import json
import mimetypes
import subprocess
import time
import uuid

from . import db, extractor, storage
from .config import MAX_BYTES, MAX_JOBS
from .errors import classify
from .urls import normalize


def run(job_id, phase, attempt):
    job = db.get(job_id)
    if not job:
        return
    state = "queued_" + phase
    with db.connect() as c:
        claimed = c.execute(
            "UPDATE jobs SET status=?,updated_at=? WHERE id=? AND status=? AND attempt=?",
            (
                "extracting" if phase == "metadata" else "downloading",
                time.time(),
                job_id,
                state,
                attempt,
            ),
        ).rowcount
    if not claimed:
        return
    if (job.get("note") or "").startswith("플랫폼 요청 제한"):
        db.update(job_id, note=None)
    try:
        if phase == "metadata":
            inspect(job)
        else:
            fetch(job)
    except Exception as exc:
        if phase == "download" and job["platform"] != "recording":
            storage.purge_partial(job)
        db.fail(job_id, *classify(exc))


def inspect(job):
    info = extractor.extract(job)
    if extractor.is_collection(info):
        limit = (
            job["options"].get("collection_limit", 25)
            if job["platform"] == "youtube"
            else (20 if job["platform"] == "instagram" else 100)
        )
        items = extractor.entries(info, limit)
        if not items:
            raise ValueError("No video")
        if job["platform"] != "instagram" and not job["options"].get("collections"):
            # Multi-video posts (X / Threads / Facebook) are also safe to expand, up to 20.
            if job["platform"] == "youtube":
                raise ValueError("No video: collection disabled")
        truncated = len(items) > limit
        with db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if (
                c.execute("SELECT count(*) FROM jobs").fetchone()[0]
                + min(len(items), limit)
                > MAX_JOBS
            ):
                raise ValueError("JOB_LIMIT")
            current_options = json.loads(
                c.execute(
                    "SELECT options FROM jobs WHERE id=?", (job["id"],)
                ).fetchone()["options"]
            )
            seen = set()
            seen_media = set()
            for index, entry in enumerate(items[:limit]):
                if job["mode"] == "audio" and entry.get("media_type") == "image":
                    continue
                media_id = str(entry.get("id") or "")
                if job["platform"] != "youtube" and media_id:
                    if media_id in seen_media:
                        continue
                    seen_media.add(media_id)
                source = job["url"]
                entry_index = index
                if job["platform"] == "youtube":
                    candidate = entry.get("webpage_url") or entry.get("url")
                    if candidate and len(candidate) == 11:
                        candidate = "https://www.youtube.com/watch?v=" + candidate
                    try:
                        source, platform = normalize(candidate or "", False)
                    except ValueError:
                        continue
                    if platform != "youtube" or source in seen:
                        continue
                    seen.add(source)
                    entry_index = None
                duplicate = c.execute(
                    "SELECT id FROM jobs WHERE batch_id=? AND url=? AND entry_index IS ?",
                    (job["batch_id"], source, entry_index),
                ).fetchone()
                if duplicate:
                    continue
                child = db.insert(
                    c,
                    url=source,
                    platform=job["platform"],
                    batch_id=job["batch_id"],
                    mode="audio" if entry.get("media_type") == "audio" else job["mode"],
                    options={**current_options, "collections": False},
                    snapshot=job["settings"],
                    parent_id=job["id"],
                    entry_index=entry_index,
                )
                c.execute(
                    "UPDATE jobs SET metadata=? WHERE id=?",
                    (json.dumps(extractor.metadata(entry), ensure_ascii=False), child),
                )
        db.update(
            job["id"],
            status="expanded",
            metadata=extractor.metadata(info),
            note=f"최대 {limit}개까지 등록했습니다. "
            + (
                "목록이 더 있어 일부만 가져왔습니다."
                if truncated
                else "하위 항목에서 메타데이터를 확인하세요."
            ),
        )
    else:
        extractor.verify_media(info, job["mode"])
        with db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            current = json.loads(
                c.execute(
                    "SELECT options FROM jobs WHERE id=?", (job["id"],)
                ).fetchone()["options"]
            )
            auto = current.get("auto_download", False)
            c.execute(
                "UPDATE jobs SET status=?,phase=?,attempt=attempt+?,metadata=?,progress=0,error_code=NULL,error_message=NULL,updated_at=? WHERE id=?",
                (
                    "queued_download" if auto else "ready",
                    "download" if auto else "metadata",
                    int(auto),
                    json.dumps(extractor.metadata(info), ensure_ascii=False),
                    time.time(),
                    job["id"],
                ),
            )


def finish(job, path, meta):
    now = time.time()
    with db.connect() as c:
        c.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?)",
            (
                uuid.uuid4().hex,
                job["id"],
                str(path),
                path.name,
                path.stat().st_size,
                mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            ),
        )
        c.execute(
            "UPDATE jobs SET status=?,metadata=?,progress=100,finished_at=?,expires_at=?,updated_at=?,error_code=NULL,error_message=NULL WHERE id=?",
            (
                "completed",
                json.dumps(meta, ensure_ascii=False),
                now,
                db.expiration(job, now),
                now,
                job["id"],
            ),
        )


def fetch(job):
    if job["platform"] == "recording":
        target = storage.directory(job)
        raw = storage.safe_path(target / job["options"]["source_name"])
        output = target / (storage.filename(job, job["metadata"]) + ".mp4")
        db.update(job["id"], progress=10)
        result = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(raw),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-vf",
                "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(output),
            ],
            capture_output=True,
            timeout=1800,
        )
        if result.returncode:
            raise ValueError("Recording conversion failed")
        if output.stat().st_size > MAX_BYTES:
            raise ValueError("SIZE_LIMIT")
        probe = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(output),
                ],
                timeout=20,
            )
        )
        video = next(s for s in probe["streams"] if s.get("codec_type") == "video")
        meta = {
            **job["metadata"],
            "width": video["width"],
            "height": video["height"],
            "max_height": video["height"],
            "duration": float(probe["format"]["duration"]),
            "codecs": [s["codec_name"] for s in probe["streams"]],
        }
        finish(job, output, meta)
        raw.unlink(missing_ok=True)
        return
    storage.purge_partial(job)
    target = storage.directory(job)
    path, meta = extractor.download(
        job,
        target,
        storage.filename(job, job["metadata"]),
        lambda n: db.update(job["id"], progress=n),
    )
    finish(job, path, meta)
