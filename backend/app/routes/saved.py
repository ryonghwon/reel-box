import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from .. import db, saved_import
from ..config import MAX_JOBS
from ..schemas import ImportProgress

router = APIRouter()


@router.post("/api/imports/instagram-saved")
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


@router.get("/api/imports/instagram-saved/draft")
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


@router.put("/api/imports/instagram-saved/draft")
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


@router.delete("/api/imports/instagram-saved/draft")
def clear_import_draft():
    with db.connect() as c:
        c.execute("DELETE FROM import_drafts WHERE id=1")
    return {"cleared": True}
