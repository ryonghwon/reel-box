import asyncio
import hashlib
import json
import time
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .. import db, storage
from ..config import DESKTOP, MAX_BYTES, MAX_JOBS
from ..schemas import BrowserMetadata, BrowserOutcome, BrowserPostComplete, Selection
from ..urls import normalize

router = APIRouter()


@router.post("/api/imports/browser-media")
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
        from ..browser_import import finish

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


@router.get("/api/imports/browser-media/{job_id}/preview")
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


@router.post("/api/imports/browser-targets")
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


@router.post("/api/imports/browser-outcome")
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


@router.post("/api/imports/browser-complete-post")
def browser_complete_post(value: BrowserPostComplete):
    if not DESKTOP:
        raise HTTPException(404)
    from ..browser_reconcile import merge_failed

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


@router.post("/api/imports/browser-metadata")
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
