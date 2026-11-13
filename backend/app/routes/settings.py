import json
import os
import shutil
import tempfile
import time
from importlib.metadata import version
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from .. import db, storage
from ..config import DESKTOP, MAX_BYTES, REDIS_URL, ROOT, WORKERS
from ..schemas import Preferences, StorageLocation

router = APIRouter()


@router.get("/api/health")
def health(request: Request):
    queue = False
    workers = 0
    if DESKTOP:
        runner = getattr(request.app.state, "local_queue", None)
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


@router.get("/api/settings")
def get_settings():
    return {
        **db.settings(),
        "storage_root": str(ROOT),
        "host_storage_root": os.getenv("DOWNLOAD_HOST_PATH", str(ROOT)),
        "max_file_bytes": MAX_BYTES,
        "download_directory": str(storage.library_path()),
    }


@router.put("/api/settings")
def save_settings(value: Preferences):
    with db.connect() as c:
        for k, v in value.model_dump().items():
            c.execute(
                "INSERT OR REPLACE INTO settings VALUES (?,?)", (k, json.dumps(v))
            )
        if value.retention_days == 0:
            db.disable_retention(c)
    return get_settings()


@router.post("/api/storage/location")
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
