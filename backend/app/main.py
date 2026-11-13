import asyncio
import hashlib
import csv
import hmac
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Literal
import zipstream
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from . import db, storage, saved_import
from .config import TOKEN, ROOT, MAX_BYTES, MAX_JOBS, REDIS_URL, DESKTOP, WORKERS
from .urls import normalize


@asynccontextmanager
async def lifespan(app):
    if len(TOKEN) < 24:
        raise RuntimeError("API_TOKEN must contain at least 24 characters")
    db.init()
    if DESKTOP:
        from .browser_reconcile import reconcile_existing

        reconcile_existing()
    runner = None
    if DESKTOP:
        from .desktop_queue import LocalQueue

        runner = LocalQueue()
        runner.start()
        app.state.local_queue = runner
    try:
        yield
    finally:
        if runner:
            runner.stop()


def authorize(x_api_key: str = Header(default="")):
    if not TOKEN or not hmac.compare_digest(TOKEN, x_api_key):
        raise HTTPException(401, "인증되지 않은 요청입니다.")


app = FastAPI(
    title="Reel Box",
    version="1.5.0",
    lifespan=lifespan,
    dependencies=[Depends(authorize)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class Registration(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=100)
    mode: Literal["video", "audio"] = "video"
    collections: bool = False
    collection_limit: int = Field(default=25, ge=1, le=100)
    auto_download: bool = False
    source: Literal["links", "instagram_saved"] = "links"
    output_format: Literal["mp4", "original"] = "mp4"


class Selection(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=100000)


class ImportProgress(BaseModel):
    draft_id: str = Field(max_length=32)
    cursor: int = Field(ge=0, le=20000)
    added: int = Field(ge=0, le=20000)
    duplicates: int = Field(ge=0, le=20000)
    auto: bool = True


class DownloadPreferences(BaseModel):
    output_format: Literal["mp4", "original"] = "mp4"
    height: int | None = Field(default=None, ge=144, le=16384)


class Preferences(BaseModel):
    folder: str = "Reelbox"
    retention_days: int = Field(default=0, ge=0, le=365)
    filename_template: str = "{date}_{platform}_{title}_{id}"

    @field_validator("folder")
    @classmethod
    def folder_valid(cls, v):
        storage.folder_path(v)
        return v

    @field_validator("filename_template")
    @classmethod
    def template_valid(cls, v):
        return storage.validate_template(v)


@app.get("/api/health")
def health():
    queue = False
    workers = 0
    if DESKTOP:
        runner = getattr(app.state, "local_queue", None)
        queue = bool(runner and runner.alive)
        workers = WORKERS if queue else 0
    else:
        try:
            from redis import Redis
            from rq import Worker

            r = Redis.from_url(REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
            queue = r.ping()
            workers = len(Worker.all(connection=r))
        except Exception:
            pass
    with db.connect() as c:
        cooldowns = [
            dict(r)
            for r in c.execute(
                "SELECT platform,until FROM platform_cooldowns WHERE until>?",
                (time.time(),),
            )
        ]
    return {
        "cooldowns": cooldowns,
        "ok": True,
        "queue": queue,
        "workers": workers,
        "desktop": DESKTOP,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "yt_dlp": version("yt-dlp"),
        "free_bytes": storage_free_bytes(),
    }


def storage_free_bytes():
    target = storage.library_path()
    while not target.exists() and target != target.parent:
        target = target.parent
    return shutil.disk_usage(target).free


@app.get("/api/settings")
def get_settings():
    return {
        **db.settings(),
        "storage_root": str(ROOT),
        "host_storage_root": os.getenv("DOWNLOAD_HOST_PATH", str(ROOT)),
        "max_file_bytes": MAX_BYTES,
        "download_directory": str(storage.library_path()),
    }


@app.put("/api/settings")
def save_settings(value: Preferences):
    with db.connect() as c:
        for k, v in value.model_dump().items():
            c.execute(
                "INSERT OR REPLACE INTO settings VALUES (?,?)", (k, json.dumps(v))
            )
        if value.retention_days == 0:
            db.disable_retention(c)
    return get_settings()


class StorageLocation(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


@app.post("/api/storage/location")
def choose_storage(value: StorageLocation):
    if not DESKTOP:
        raise HTTPException(403, "앱에서 저장 폴더를 선택하세요.")
    target = Path(value.path).expanduser()
    if not target.is_absolute():
        raise HTTPException(400, "전체 폴더 경로가 필요합니다.")
    target = target.resolve()
    if target == target.parent or not target.is_dir():
        raise HTTPException(400, "사용할 폴더를 선택하세요.")
    try:
        with tempfile.TemporaryFile(dir=target):
            pass
    except OSError:
        raise HTTPException(
            400, "이 폴더에 쓸 수 없습니다. 접근 권한과 연결 상태를 확인하세요."
        )
    with db.connect() as c:
        c.execute("INSERT OR IGNORE INTO storage_locations VALUES (?)", (str(target),))
        c.execute(
            "INSERT OR REPLACE INTO settings VALUES ('download_directory',?)",
            (json.dumps(str(target)),),
        )
    return get_settings()


@app.post("/api/jobs")
def register(value: Registration):
    batch = uuid.uuid4().hex
    added = []
    duplicates = []
    rejected = []
    seen = set()
    snapshot = db.settings()
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        existing_count = c.execute("SELECT count(*) FROM jobs").fetchone()[0]
        for raw in value.urls:
            try:
                url, platform = normalize(raw, value.collections)
            except ValueError as e:
                rejected.append({"url": raw[:2048], "reason": str(e)})
                continue
            old = c.execute(
                "SELECT id FROM jobs WHERE url=? AND mode=? AND platform=? AND entry_index IS NULL ORDER BY created_at DESC LIMIT 1",
                (url, value.mode, platform),
            ).fetchone()
            if url in seen or old:
                if old and value.source == "instagram_saved":
                    for row in c.execute(
                        "WITH RECURSIVE family(id) AS (SELECT ? UNION SELECT jobs.id FROM jobs JOIN family ON jobs.parent_id=family.id) SELECT id,options,status FROM jobs WHERE id IN (SELECT id FROM family)",
                        (old["id"],),
                    ).fetchall():
                        options = json.loads(row["options"])
                        options["source"] = "instagram_saved"
                        if value.auto_download:
                            options["auto_download"] = True
                        c.execute(
                            "UPDATE jobs SET options=?,updated_at=? WHERE id=?",
                            (json.dumps(options), time.time(), row["id"]),
                        )
                        if value.auto_download and row["status"] == "ready":
                            c.execute(
                                "UPDATE jobs SET status='queued_download',phase='download',attempt=attempt+1,updated_at=? WHERE id=?",
                                (time.time(), row["id"]),
                            )
                duplicates.append({"url": url, "id": old["id"] if old else None})
                continue
            if existing_count + len(added) >= MAX_JOBS:
                raise HTTPException(
                    409,
                    f"작업 보관함의 {MAX_JOBS:,}개 한도에 도달했습니다. 이번 묶음은 등록되지 않았으며 남은 목록을 이어서 처리할 수 있습니다.",
                )
            seen.add(url)
            jid = db.insert(
                c,
                url=url,
                platform=platform,
                batch_id=batch,
                mode=value.mode,
                options={
                    "collections": value.collections,
                    "collection_limit": value.collection_limit,
                    "auto_download": value.auto_download,
                    "source": value.source,
                    "output_format": value.output_format,
                },
                snapshot=snapshot,
            )
            added.append(jid)
    return {
        "batch_id": batch,
        "added": added,
        "duplicates": duplicates,
        "rejected": rejected,
    }


@app.post("/api/imports/instagram-saved")
async def preview_saved(request: Request, filename: str = "export.zip"):
    if len(filename) > 240:
        raise HTTPException(400, "파일 이름이 너무 깁니다.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > saved_import.UPLOAD_LIMIT:
            raise HTTPException(
                413,
                "32MB 이하 파일만 가져올 수 있습니다. ZIP을 풀고 saved_posts 파일만 선택하세요.",
            )
    try:
        result = saved_import.parse_export(bytes(raw), filename)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with db.connect() as c:
        existing = {
            r[0]
            for r in c.execute(
                "SELECT url FROM jobs WHERE mode='video' AND platform='instagram' AND entry_index IS NULL"
            )
        }
        count = c.execute("SELECT count(*) FROM jobs").fetchone()[0]
    result["already_registered"] = sum(url in existing for url in result["urls"])
    result["available_slots"] = max(0, MAX_JOBS - count)
    result["job_limit"] = MAX_JOBS
    result["draft_id"] = uuid.uuid4().hex
    draft = {
        "preview": result,
        "filename": Path(filename).name,
        "cursor": 0,
        "added": 0,
        "duplicates": 0,
        "auto": True,
    }
    with db.connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO import_drafts VALUES (1,?)",
            (json.dumps(draft, ensure_ascii=False),),
        )
    return result


@app.get("/api/imports/instagram-saved/draft")
def get_import_draft():
    with db.connect() as c:
        row = c.execute("SELECT payload FROM import_drafts WHERE id=1").fetchone()
        if not row:
            return {"draft": None}
        draft = json.loads(row["payload"])
        count = c.execute("SELECT count(*) FROM jobs").fetchone()[0]
    draft["preview"].update(
        job_limit=MAX_JOBS, available_slots=max(0, MAX_JOBS - count)
    )
    return {"draft": draft}


@app.put("/api/imports/instagram-saved/draft")
def update_import_draft(value: ImportProgress):
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT payload FROM import_drafts WHERE id=1").fetchone()
        draft = json.loads(row["payload"]) if row else None
        if not draft or draft["preview"]["draft_id"] != value.draft_id:
            raise HTTPException(
                409, "다른 목록을 가져왔습니다. 현재 목록을 다시 확인하세요."
            )
        if value.cursor > len(draft["preview"]["urls"]):
            raise HTTPException(422, "목록 범위를 넘는 진행 상태입니다.")
        draft.update(value.model_dump(exclude={"draft_id"}))
        c.execute(
            "UPDATE import_drafts SET payload=? WHERE id=1",
            (json.dumps(draft, ensure_ascii=False),),
        )
    return {"saved": True}


@app.delete("/api/imports/instagram-saved/draft")
def clear_import_draft():
    with db.connect() as c:
        c.execute("DELETE FROM import_drafts WHERE id=1")
    return {"cleared": True}


@app.get("/api/jobs")
def list_jobs(since: float = 0):
    with db.connect() as c:
        c.execute("BEGIN")
        server_time = time.time()
        jobs = [
            db.decode(r)
            for r in c.execute(
                "SELECT * FROM jobs WHERE updated_at>=? ORDER BY created_at DESC",
                (max(0, since),),
            )
        ]
        all_ids = [r[0] for r in c.execute("SELECT id FROM jobs")] if since else None
        files = {}
        for row in c.execute(
            "SELECT f.id,f.job_id,f.name,f.size,f.mime FROM files f JOIN jobs j ON j.id=f.job_id WHERE j.updated_at>=?",
            (max(0, since),),
        ):
            files.setdefault(row["job_id"], []).append(dict(row))
    for j in jobs:
        j["files"] = files.get(j["id"], [])
        j.pop("queue_id", None)
    return {"jobs": jobs, "server_time": server_time, "all_ids": all_ids}


@app.post("/api/jobs/start")
def start(value: Selection):
    updated = []
    wanted = set(value.ids)
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        for row in c.execute("SELECT id FROM jobs WHERE status='ready'").fetchall():
            if wanted and row["id"] not in wanted:
                continue
            c.execute(
                "UPDATE jobs SET status='queued_download',phase='download',attempt=attempt+1,updated_at=? WHERE id=?",
                (time.time(), row["id"]),
            )
            updated.append(row["id"])
    return {"updated": updated}


@app.put("/api/jobs/{job_id}/preferences")
def download_preferences(job_id: str, value: DownloadPreferences):
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = db.decode(
            c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        )
        if not row:
            raise HTTPException(404, "작업을 찾을 수 없습니다.")
        if row["status"] != "ready" or row["mode"] != "video":
            raise HTTPException(
                409, "다운로드 준비 상태의 영상에서만 화질을 바꿀 수 있습니다."
            )
        available = row["metadata"].get("available_heights", [])
        if value.height is not None and value.height not in available:
            raise HTTPException(
                422,
                "이 영상에 제공되지 않는 해상도입니다. 목록에 표시된 화질을 선택하세요.",
            )
        opts = {**row["options"], **value.model_dump()}
        c.execute(
            "UPDATE jobs SET options=?,updated_at=? WHERE id=?",
            (json.dumps(opts), time.time(), job_id),
        )
    return {"id": job_id, "options": opts}


@app.post("/api/jobs/retry")
def retry(value: Selection):
    updated = []
    wanted = set(value.ids)
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        for row in c.execute(
            "SELECT id,phase FROM jobs WHERE status='failed' AND retryable=1"
        ).fetchall():
            if wanted and row["id"] not in wanted:
                continue
            c.execute(
                "UPDATE jobs SET status=?,attempt=attempt+1,error_code=NULL,error_message=NULL,progress=0,updated_at=? WHERE id=?",
                ("queued_" + row["phase"], time.time(), row["id"]),
            )
            updated.append(row["id"])
    return {"updated": updated}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = db.decode(
            c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        )
        if not row:
            raise HTTPException(404, "작업을 찾을 수 없습니다.")
        if row["status"] not in ("ready", "failed", "completed", "expired", "expanded"):
            raise HTTPException(409, "진행 중인 작업은 삭제할 수 없습니다.")
        storage.purge_partial(row)
        c.execute("DELETE FROM files WHERE job_id=?", (job_id,))
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return {"deleted": job_id}


@app.post("/api/jobs/delete")
def delete_jobs(value: Selection):
    if not value.ids:
        raise HTTPException(422, "삭제할 항목을 선택하세요.")
    wanted = set(value.ids)
    deleted = []
    skipped = []
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        rows = [
            db.decode(r) for r in c.execute("SELECT * FROM jobs") if r["id"] in wanted
        ]
        for row in rows:
            if row["status"] in ("extracting", "downloading", "recording", "expiring"):
                skipped.append(row["id"])
                continue
            try:
                storage.purge_partial(row)
            except PermissionError:
                skipped.append(row["id"])
                continue
            c.execute("DELETE FROM files WHERE job_id=?", (row["id"],))
            c.execute("DELETE FROM jobs WHERE id=?", (row["id"],))
            deleted.append(row["id"])
    return {"deleted": deleted, "skipped": skipped}


@app.post("/api/jobs/{job_id}/compatible")
def compatible(job_id: str):
    original = db.get(job_id)
    if (
        not original
        or original["status"] != "completed"
        or original["mode"] != "video"
        or original["metadata"].get("media_type") in ("image", "audio")
    ):
        raise HTTPException(409, "완료된 영상만 MP4로 변환할 수 있습니다.")
    snapshot = db.settings()
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT count(*) FROM jobs").fetchone()[0] >= MAX_JOBS:
            raise HTTPException(409, "작업 기록 한도를 초과했습니다.")
        file = c.execute("SELECT * FROM files WHERE job_id=?", (job_id,)).fetchone()
        if not file or not storage.safe_path(file["path"]).is_file():
            raise HTTPException(410, "원본 파일이 만료되었습니다.")
        jid = db.insert(
            c,
            url=original["url"],
            platform="recording",
            batch_id=uuid.uuid4().hex,
            snapshot=snapshot,
            status="recording",
            parent_id=job_id,
        )
        # The transaction pins the source against retention while copying.
        job = {"id": jid, "settings": snapshot}
        target = storage.directory(job)
        raw = target / (".source" + Path(file["name"]).suffix)
        try:
            shutil.copyfile(storage.safe_path(file["path"]), raw)
        except OSError:
            storage.purge_partial(job)
            raise HTTPException(507, "변환용 파일을 복사할 저장 공간이 부족합니다.")
        meta = {
            **original["metadata"],
            "title": original["metadata"].get("title", "영상") + " · MP4",
        }
        c.execute(
            "UPDATE jobs SET phase='download',status='queued_download',options=?,metadata=?,note=?,expires_at=? WHERE id=?",
            (
                json.dumps(
                    {
                        "source_name": raw.name,
                        "source": original["options"].get("source", "links"),
                    }
                ),
                json.dumps(meta, ensure_ascii=False),
                "원본을 유지한 H.264/AAC MP4 720p 호환본",
                time.time() + 86400,
                jid,
            ),
        )
    return {"id": jid}


@app.get("/api/files/{file_id}")
def file(file_id: str):
    with db.connect() as c:
        row = c.execute(
            "SELECT f.* FROM files f JOIN jobs j ON j.id=f.job_id WHERE f.id=? AND j.status='completed' AND (j.expires_at IS NULL OR j.expires_at>?)",
            (file_id, time.time()),
        ).fetchone()
    if not row:
        raise HTTPException(404, "파일이 없거나 보관 기간이 지났습니다.")
    path = storage.safe_path(row["path"])
    if not path.is_file():
        raise HTTPException(410, "저장된 파일을 찾을 수 없습니다.")
    return FileResponse(
        path,
        filename=row["name"],
        media_type=row["mime"],
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/exports")
def export_selection(value: Selection):
    token = uuid.uuid4().hex
    with db.connect() as c:
        c.execute("DELETE FROM exports WHERE expires_at<?", (time.time(),))
        c.execute(
            "INSERT INTO exports VALUES (?,?,?)",
            (token, json.dumps(value.ids), time.time() + 3600),
        )
    return {"selection": token}


def selected_jobs(ids, selection=""):
    wanted = set(filter(None, (ids or "").split(",")))
    if selection:
        with db.connect() as c:
            row = c.execute(
                "SELECT ids FROM exports WHERE id=? AND expires_at>?",
                (selection, time.time()),
            ).fetchone()
        if not row:
            raise HTTPException(
                410, "내보내기 선택이 만료되었습니다. 다시 다운로드 버튼을 누르세요."
            )
        wanted = set(json.loads(row["ids"]))
    return [j for j in list_jobs()["jobs"] if not wanted or j["id"] in wanted]


def csv_bytes(jobs):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(
        [
            "job_id",
            "platform",
            "source_url",
            "title",
            "uploader",
            "mode",
            "status",
            "error_code",
            "filename",
            "bytes",
            "created_at_utc",
            "expires_at_utc",
        ]
    )

    def safe(value):
        s = str(value if value is not None else "")
        return "'" + s if s.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else s

    for j in jobs:
        for f in j["files"] or [{}]:
            values = [
                j["id"],
                j["platform"],
                j["url"],
                j["metadata"].get("title", ""),
                j["metadata"].get("uploader", ""),
                j["mode"],
                j["status"],
                j["error_code"],
                f.get("name", ""),
                f.get("size", ""),
                datetime.fromtimestamp(j["created_at"], timezone.utc).isoformat(),
                datetime.fromtimestamp(j["expires_at"], timezone.utc).isoformat()
                if j["expires_at"]
                else "",
            ]
            writer.writerow([safe(v) for v in values])
    return ("\ufeff" + out.getvalue()).encode("utf-8")


@app.get("/api/manifest.csv")
def manifest(ids: str = "", selection: str = ""):
    return Response(
        csv_bytes(selected_jobs(ids, selection)),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="reelbox-manifest.csv"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/archive.zip")
def archive(ids: str = "", selection: str = ""):
    jobs = selected_jobs(ids, selection)
    z = zipstream.ZipStream(compress_type=zipstream.ZIP_STORED)
    count = 0
    # Snapshot directory entries instead of opening thousands of file descriptors.
    # Hard links survive retention/deletion without copying media on normal local disks.
    snapshot = tempfile.TemporaryDirectory(prefix=".reelbox-export-", dir=ROOT)

    def chunks(path):
        with path.open("rb") as handle:
            while data := handle.read(1024 * 1024):
                yield data

    try:
        with db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            for j in jobs:
                current = c.execute(
                    "SELECT status,expires_at FROM jobs WHERE id=?", (j["id"],)
                ).fetchone()
                if (
                    not current
                    or current["status"] != "completed"
                    or (
                        current["expires_at"] is not None
                        and current["expires_at"] <= time.time()
                    )
                ):
                    continue
                for f in c.execute("SELECT * FROM files WHERE job_id=?", (j["id"],)):
                    original = storage.safe_path(f["path"])
                    pinned = Path(snapshot.name) / str(count)
                    try:
                        try:
                            os.link(original, pinned)
                        except FileNotFoundError:
                            continue
                        except OSError:
                            shutil.copyfile(original, pinned)
                    except FileNotFoundError:
                        continue
                    except OSError as error:
                        raise HTTPException(
                            507,
                            "ZIP 파일을 준비할 저장 공간이나 파일 권한을 확인하세요.",
                        ) from error
                    z.add(chunks(pinned), arcname=f["name"], size=f["size"])
                    count += 1
        if not count:
            raise HTTPException(404, "다운로드할 완료 파일이 없습니다.")
        z.add(csv_bytes(jobs), arcname="manifest.csv")
    except BaseException:
        snapshot.cleanup()
        raise

    def stream():
        try:
            yield from z
        finally:
            snapshot.cleanup()

    return StreamingResponse(
        stream(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="reelbox.zip"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/recordings")
async def recording(request: Request, title: str = "화면 녹화", source: str = ""):
    if len(title) > 200 or len(source) > 2048:
        raise HTTPException(400, "제목이나 링크가 너무 깁니다.")
    mime = request.headers.get("content-type", "").split(";")[0]
    if mime not in ("video/webm", "video/mp4"):
        raise HTTPException(415, "WebM 또는 MP4 녹화 파일이 필요합니다.")
    if source:
        try:
            source, _ = normalize(source)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    snapshot = db.settings()
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT count(*) FROM jobs").fetchone()[0] >= MAX_JOBS:
            raise HTTPException(409, "작업 기록 한도를 초과했습니다.")
        jid = db.insert(
            c,
            url=source,
            platform="recording",
            batch_id=uuid.uuid4().hex,
            snapshot=snapshot,
            status="recording",
        )
    job = db.get(jid)
    try:
        target = storage.directory(job)
        raw = target / (".source.mp4" if mime == "video/mp4" else ".source.webm")
        total = 0
        last = time.monotonic()
        with raw.open("wb") as f:
            async for chunk in request.stream():
                total += len(chunk)
                if total > min(MAX_BYTES, 512 * 1024**2):
                    raise HTTPException(413, "녹화 파일은 512MB 이하로 저장하세요.")
                f.write(chunk)
                if time.monotonic() - last > 5:
                    db.update(jid, progress=0)
                    last = time.monotonic()
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(raw),
            ],
            capture_output=True,
            timeout=20,
        )
        info = json.loads(probe.stdout or "{}")
        videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
        if probe.returncode or not videos:
            raise HTTPException(422, "유효한 영상 파일이 아닙니다.")
        meta = {
            "title": title,
            "id": jid[:8],
            "duration": float(info.get("format", {}).get("duration") or 0),
            "width": videos[0].get("width"),
            "height": videos[0].get("height"),
        }
        db.update(
            jid,
            status="queued_download",
            phase="download",
            metadata=meta,
            options={"source_name": raw.name},
            note="사용자가 선택한 화면 녹화 · MP4 720p/30fps 변환",
            expires_at=time.time() + 86400,
        )
        return {"id": jid}
    except BaseException as exc:
        storage.purge_partial(job)
        db.fail(
            jid,
            "UPLOAD_FAILED",
            "녹화 업로드에 실패했습니다. 브라우저에 남아 있는 파일을 다시 저장하세요.",
        )
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(422, "녹화 파일을 처리하지 못했습니다.") from exc


@app.post("/api/imports/browser-media")
async def browser_media(
    request: Request,
    source: str,
    title: str = "",
    kind: Literal["image", "video"] = "video",
    uploader: str = "",
    target_id: str = "",
    post_index: int | None = None,
    asset_id: str = "",
    silent: bool = False,
    defer_merge: bool = False,
):
    if not DESKTOP:
        raise HTTPException(404, "데스크톱 앱에서만 사용할 수 있습니다.")
    if (
        len(source) > 2048
        or len(title) > 200
        or len(uploader) > 100
        or len(target_id) > 64
        or len(asset_id) > 80
    ):
        raise HTTPException(400, "미디어 정보가 너무 깁니다.")
    try:
        source, platform = normalize(source)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if platform != "instagram":
        raise HTTPException(400, "Instagram 게시물만 이 창에서 저장할 수 있습니다.")
    if target_id:
        target = db.get(target_id)
        if not target or target["url"] != source or target["platform"] != platform:
            raise HTTPException(409, "기존 항목과 게시물 링크가 일치하지 않습니다.")
        if target["status"] not in ("failed", "completed"):
            raise HTTPException(
                409, "기존 작업이 처리 중입니다. 완료된 뒤 다시 시도하세요."
            )
        if target["parent_id"] and target["entry_index"] != post_index:
            raise HTTPException(409, "게시물 안의 미디어 순서가 일치하지 않습니다.")
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT count(*) FROM jobs").fetchone()[0] >= MAX_JOBS:
            raise HTTPException(409, "작업 기록 한도를 초과했습니다.")
        jid = db.insert(
            c,
            url=source,
            platform=platform,
            batch_id=uuid.uuid4().hex,
            snapshot=db.settings(),
            status="recording",
            options={"source": "browser"},
        )
    job = db.get(jid)
    try:
        raw = storage.directory(job) / ".browser-upload"
        total = 0
        digest = hashlib.sha256()
        with raw.open("wb") as out:
            async for chunk in request.stream():
                total += len(chunk)
                if total > min(
                    MAX_BYTES, 64 * 1024**2 if kind == "image" else 2 * 1024**3
                ):
                    raise HTTPException(
                        413, "이미지는 64MB, 영상은 2GB 이하로 저장하세요."
                    )
                digest.update(chunk)
                out.write(chunk)
        from .browser_import import finish

        return await asyncio.to_thread(
            finish,
            jid,
            raw,
            source,
            title,
            kind,
            digest.hexdigest(),
            uploader,
            target_id,
            post_index,
            asset_id,
            silent,
            defer_merge,
        )
    except BaseException as exc:
        storage.purge_partial(job)
        db.fail(
            jid,
            "BROWSER_SAVE_FAILED",
            "로그인 창의 미디어 저장이 실패했습니다. 미디어를 다시 확인하세요.",
        )
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            422,
            str(exc)
            if isinstance(exc, ValueError)
            else "미디어 파일을 확인하지 못했습니다.",
        ) from exc


@app.get("/api/imports/browser-media/{job_id}/preview")
def browser_media_preview(job_id: str):
    job = db.get(job_id)
    if (
        not job
        or job["status"] != "completed"
        or not (
            job["options"].get("source") == "browser"
            or job["options"].get("browser_import")
        )
    ):
        raise HTTPException(404)
    target = storage.safe_path(storage.job_path(job) / ".preview.jpg")
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, media_type="image/jpeg")


@app.post("/api/imports/browser-targets")
def browser_targets(value: Selection):
    if not DESKTOP:
        raise HTTPException(404)
    if not value.ids or len(value.ids) > 500:
        raise HTTPException(422, "1~500개 항목을 선택하세요.")
    wanted = set(value.ids)
    groups = {}
    with db.connect() as c:
        for row in c.execute(
            "SELECT * FROM jobs WHERE platform='instagram' AND mode='video' AND status IN ('failed','completed') ORDER BY created_at"
        ):
            job = db.decode(row)
            if job["id"] not in wanted:
                continue
            if job["status"] == "completed" and not (
                job["options"].get("browser_import")
                or job["options"].get("source") == "browser"
            ):
                continue
            if job["error_code"] in ("DRM_PROTECTED", "UNSUPPORTED_URL"):
                continue
            groups.setdefault(job["url"], []).append(
                {
                    "id": job["id"],
                    "index": job["entry_index"] if job["parent_id"] else None,
                    "status": job["status"],
                }
            )
    return {"posts": [{"url": url, "targets": items} for url, items in groups.items()]}


class BrowserOutcome(BaseModel):
    ids: list[str] = Field(max_length=500)
    message: str = Field(max_length=400)
    code: Literal[
        "BROWSER_LOGIN_REQUIRED",
        "BROWSER_ACCESS_RESTRICTED",
        "BROWSER_MEDIA_UNAVAILABLE",
        "BROWSER_REVIEW_REQUIRED",
        "BROWSER_SAVE_FAILED",
    ]


@app.post("/api/imports/browser-outcome")
def browser_outcome(value: BrowserOutcome):
    if not DESKTOP:
        raise HTTPException(404)
    with db.connect() as c:
        for jid in set(value.ids):
            c.execute(
                "UPDATE jobs SET note=?,updated_at=? WHERE id=? AND status='failed'",
                (value.code + ": " + value.message, time.time(), jid),
            )
    return {"ok": True}


class BrowserPostComplete(BaseModel):
    target_id: str = Field(max_length=64)
    saved_ids: list[str] = Field(min_length=1, max_length=20)


@app.post("/api/imports/browser-complete-post")
def browser_complete_post(value: BrowserPostComplete):
    if not DESKTOP:
        raise HTTPException(404)
    from .browser_reconcile import merge_failed

    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        target = db.decode(
            c.execute("SELECT * FROM jobs WHERE id=?", (value.target_id,)).fetchone()
        )
        if not target:
            return {"merged": None}
        saved = [
            db.decode(c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone())
            for jid in dict.fromkeys(value.saved_ids)
        ]
        if (
            target["status"] != "failed"
            or target["parent_id"]
            or any(
                not j
                or j["url"] != target["url"]
                or j["status"] != "completed"
                or not j["options"].get("browser_import")
                for j in saved
            )
        ):
            raise HTTPException(409, "게시물과 저장 결과가 일치하지 않습니다.")
        merged = merge_failed(c, saved[0]["id"], target["id"])
        if merged:
            for index, job in enumerate(saved[1:], 1):
                options = {
                    **job["options"],
                    "source": target["options"].get("source", "browser"),
                }
                c.execute(
                    "UPDATE jobs SET parent_id=?,entry_index=?,created_at=?,updated_at=?,options=? WHERE id=?",
                    (
                        saved[0]["id"],
                        index,
                        target["created_at"],
                        time.time(),
                        json.dumps(options),
                        job["id"],
                    ),
                )
        return {"merged": merged}


class BrowserMetadata(BaseModel):
    source: str = Field(max_length=2048)
    title: str = Field(max_length=200)
    uploader: str = Field(max_length=100)


@app.post("/api/imports/browser-metadata")
def browser_metadata(value: BrowserMetadata):
    if not DESKTOP:
        raise HTTPException(404)
    try:
        source, platform = normalize(value.source)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if platform != "instagram":
        raise HTTPException(400)
    with db.connect() as c:
        rows = c.execute(
            "SELECT * FROM jobs WHERE url=? AND status IN ('failed','completed')",
            (source,),
        ).fetchall()
        for row in rows:
            job = db.decode(row)
            if job["status"] == "completed" and not (
                job["options"].get("browser_import")
                or job["options"].get("source") == "browser"
            ):
                continue
            meta = {
                **job["metadata"],
                "webpage_url": source,
                "browser_metadata_version": 2,
            }
            if value.uploader:
                meta["uploader"] = value.uploader
            if value.title:
                meta["title"] = value.title
            c.execute(
                "UPDATE jobs SET metadata=?,updated_at=? WHERE id=?",
                (json.dumps(meta, ensure_ascii=False), time.time(), job["id"]),
            )
    return {"ok": True}
