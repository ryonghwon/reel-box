import re
import shutil
import string
from datetime import datetime, timezone
from pathlib import Path
from .config import ROOT, MIN_FREE, DESKTOP
from . import db

FIELDS = {"date", "platform", "title", "id", "uploader"}


def validate_template(template):
    if not 1 <= len(template) <= 150 or "/" in template or "\\" in template:
        raise ValueError("파일명 규칙은 경로 없이 150자 이내로 입력하세요.")
    try:
        for _, field, spec, conv in string.Formatter().parse(template):
            if field is not None and (field not in FIELDS or spec or conv):
                raise ValueError(
                    "허용된 파일명 항목만 사용하세요: date, platform, title, id, uploader"
                )
    except (ValueError, KeyError) as e:
        raise ValueError(str(e)) from e
    return template


def clean(text, limit=90):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", str(text))
    text = text.strip(" .") or "untitled"
    return text.encode("utf-8")[:limit].decode("utf-8", "ignore")


def folder_path(folder):
    if not re.fullmatch(r"[\w가-힣 .-]{1,60}", folder) or folder in (".", ".."):
        raise ValueError(
            "저장 폴더명은 1~60자의 문자·숫자·공백·점·하이픈으로 입력하세요."
        )
    p = (ROOT / folder).resolve()
    if not p.is_relative_to(ROOT):
        raise ValueError("저장 경로가 올바르지 않습니다.")
    return p


def safe_path(path):
    p = Path(path).resolve()
    roots = [ROOT]
    if DESKTOP:
        with db.connect() as c:
            roots += [
                Path(r["path"]) for r in c.execute("SELECT path FROM storage_locations")
            ]
    if not any(p.is_relative_to(root) and p != root for root in roots):
        raise ValueError("저장 경로가 올바르지 않습니다.")
    return p


def library_path(snapshot=None):
    snapshot = snapshot if snapshot is not None else db.settings()
    chosen = snapshot.get("download_directory") if DESKTOP else None
    if chosen:
        with db.connect() as c:
            if not c.execute(
                "SELECT 1 FROM storage_locations WHERE path=?", (chosen,)
            ).fetchone():
                raise ValueError("선택한 저장 폴더를 확인하세요.")
        return Path(chosen)
    return folder_path(snapshot["folder"])


def job_path(job):
    return safe_path(library_path(job["settings"]) / job["id"])


def directory(job):
    if (
        DESKTOP
        and job["settings"].get("download_directory")
        and not library_path(job["settings"]).is_dir()
    ):
        raise OSError(
            "STORAGE_UNAVAILABLE: 저장 폴더를 찾을 수 없습니다. 디스크 연결을 확인하세요."
        )
    p = job_path(job)
    p.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(p).free < MIN_FREE:
        raise OSError("DISK_FULL")
    return p


def filename(job, meta):
    data = {k: clean(meta.get(k) or "unknown") for k in FIELDS}
    data.update(
        date=datetime.now(timezone.utc).strftime("%Y%m%d"), platform=job["platform"]
    )
    title = validate_template(job["settings"]["filename_template"]).format(**data)
    return clean(title, 170) + "_" + job["id"][:8]


def purge_partial(job):
    p = job_path(job)
    if p.exists():
        shutil.rmtree(p)
