import json
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import db, storage
from ..config import MAX_JOBS
from ..job_listing import list_jobs
from ..schemas import DownloadPreferences, Registration, Selection
from ..urls import normalize

router = APIRouter()


@router.post("/api/jobs")
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


@router.post("/api/jobs/start")
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


@router.put("/api/jobs/{job_id}/preferences")
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


@router.post("/api/jobs/retry")
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


@router.delete("/api/jobs/{job_id}")
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


@router.post("/api/jobs/delete")
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


@router.post("/api/jobs/{job_id}/compatible")
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


@router.get("/api/jobs")
def jobs_since(since: float = 0):
    return list_jobs(since)
