import json
import subprocess
import time
import uuid

from fastapi import APIRouter, HTTPException, Request

from .. import db, storage
from ..config import MAX_BYTES, MAX_JOBS
from ..urls import normalize

router = APIRouter()


@router.post("/api/recordings")
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
