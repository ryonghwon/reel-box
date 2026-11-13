"""Import files explicitly selected from the desktop's normal Instagram viewer."""

import json
import subprocess
import time
import uuid
from . import db, storage


def image_extension(header):
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    if header[4:8] == b"ftyp" and any(v in header[8:40] for v in (b"avif", b"avis")):
        return "avif"
    raise ValueError("JPEG, PNG, WebP, AVIF 이미지만 저장할 수 있습니다.")


def finish(
    jid,
    raw,
    source,
    title,
    kind,
    digest,
    uploader="",
    target_id="",
    post_index=None,
    asset_id="",
    silent=False,
    defer_merge=False,
):
    job = db.get(jid)
    with raw.open("rb") as handle:
        header = handle.read(40)
    ext = image_extension(header) if kind == "image" else "mp4"
    if kind == "video" and header[4:8] != b"ftyp":
        raise ValueError("유효한 MP4 파일이 아닙니다.")
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
        timeout=30,
    )
    info = json.loads(probe.stdout or "{}")
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if (
        probe.returncode
        or not video
        or not video.get("width")
        or not video.get("height")
    ):
        raise ValueError("유효한 미디어 파일이 아닙니다.")
    if kind == "video" and video.get("codec_name") != "h264":
        raise ValueError("브라우저 영상은 H.264 MP4로 변환한 뒤 저장하세요.")
    source_id = source.rstrip("/").split("/")[-1]
    if not title or title.strip().lower() == "instagram":
        title = (uploader + " · " if uploader else "") + source_id
    meta = {
        "browser_metadata_version": 2,
        "id": source_id,
        "title": title,
        "uploader": uploader,
        "webpage_url": source,
        "browser_asset_id": asset_id,
        "media_type": kind,
        "width": video["width"],
        "height": video["height"],
        "max_height": video["height"],
        "duration": float(info.get("format", {}).get("duration") or 0)
        if kind == "video"
        else None,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams)
        if kind == "video"
        else None,
    }
    target = raw.parent / (storage.filename(job, meta) + "." + ext)
    raw.rename(target)
    fid = uuid.uuid4().hex
    mime = {
        "jpg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "avif": "image/avif",
        "mp4": "video/mp4",
    }[ext]
    if kind == "image":
        meta["thumbnail"] = "/api/files/" + fid
    else:
        thumb = target.parent / ".preview.jpg"
        preview = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(target),
                "-frames:v",
                "1",
                "-vf",
                "scale=480:-2",
                str(thumb),
            ],
            capture_output=True,
            timeout=30,
        )
        if preview.returncode == 0 and thumb.exists():
            meta["thumbnail"] = "/api/imports/browser-media/" + jid + "/preview"
    now = time.time()
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        existing = c.execute(
            "SELECT id FROM jobs WHERE id<>? AND url=? AND status='completed' AND json_extract(options,'$.browser_sha256')=? LIMIT 1",
            (jid, source, digest),
        ).fetchone()
        if existing:
            c.execute("DELETE FROM jobs WHERE id=?", (jid,))
            previous = db.decode(
                c.execute("SELECT * FROM jobs WHERE id=?", (existing["id"],)).fetchone()
            )
            fresh = {
                **previous["metadata"],
                **{
                    k: v
                    for k, v in meta.items()
                    if k in ("title", "uploader", "webpage_url", "browser_asset_id")
                    and v
                },
            }
            c.execute(
                "UPDATE jobs SET metadata=?,updated_at=? WHERE id=?",
                (json.dumps(fresh, ensure_ascii=False), now, existing["id"]),
            )
        else:
            c.execute(
                "INSERT INTO files VALUES (?,?,?,?,?,?)",
                (fid, jid, str(target), target.name, target.stat().st_size, mime),
            )
            c.execute(
                "UPDATE jobs SET status='completed',phase='download',progress=100,metadata=?,options=?,finished_at=?,expires_at=?,updated_at=?,note=? WHERE id=?",
                (
                    json.dumps(meta, ensure_ascii=False),
                    json.dumps(
                        {
                            "source": "browser",
                            "browser_import": True,
                            "browser_sha256": digest,
                            "output_format": "mp4" if kind == "video" else "original",
                        }
                    ),
                    now,
                    db.expiration(job, now),
                    now,
                    "로그인 연결로 저장 · 확인된 재생 화질"
                    + (
                        " · 오디오 스트림 없음"
                        if kind == "video" and not meta["has_audio"]
                        else ""
                    ),
                    jid,
                ),
            )
        from .browser_reconcile import merge_failed

        merged = (
            None
            if defer_merge
            else merge_failed(
                c, existing["id"] if existing else jid, target_id, post_index
            )
        )
    if existing:
        storage.purge_partial(job)
        return {"id": existing["id"], "duplicate": True, "merged": merged}
    return {"id": jid, "duplicate": False, "merged": merged}
