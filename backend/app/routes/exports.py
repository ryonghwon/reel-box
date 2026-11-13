import csv
import io
import json
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import zipstream
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse

from .. import db, storage
from ..config import ROOT
from ..job_listing import list_jobs
from ..schemas import Selection

router = APIRouter()


@router.get("/api/files/{file_id}")
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


@router.post("/api/exports")
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


@router.get("/api/manifest.csv")
def manifest(ids: str = "", selection: str = ""):
    return Response(
        csv_bytes(selected_jobs(ids, selection)),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="reelbox-manifest.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/api/archive.zip")
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
