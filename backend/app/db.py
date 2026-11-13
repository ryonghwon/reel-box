import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from .config import DATA, ROOT

DEFAULTS = {
    "folder": "Reelbox",
    "retention_days": 0,
    "filename_template": "{date}_{platform}_{title}_{id}",
}


@contextmanager
def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATA / "reelbox.sqlite3", timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def init():
    ROOT.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, url TEXT NOT NULL, platform TEXT NOT NULL,
          status TEXT NOT NULL, phase TEXT NOT NULL DEFAULT 'metadata', mode TEXT NOT NULL DEFAULT 'video',
          options TEXT NOT NULL DEFAULT '{}', settings TEXT NOT NULL DEFAULT '{}', metadata TEXT NOT NULL DEFAULT '{}',
          parent_id TEXT, entry_index INTEGER, progress REAL NOT NULL DEFAULT 0,
          error_code TEXT, error_message TEXT, retryable INTEGER NOT NULL DEFAULT 0,
          attempt INTEGER NOT NULL DEFAULT 0, queue_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
          finished_at REAL, expires_at REAL, note TEXT, UNIQUE(batch_id, url, entry_index)
        );
        CREATE TABLE IF NOT EXISTS files (
          id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), path TEXT NOT NULL,
          name TEXT NOT NULL, size INTEGER NOT NULL, mime TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS exports (id TEXT PRIMARY KEY, ids TEXT NOT NULL, expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS import_drafts (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS storage_locations (path TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS platform_cooldowns (platform TEXT PRIMARY KEY, until REAL NOT NULL, strikes INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS jobs_updated ON jobs(updated_at);
        CREATE INDEX IF NOT EXISTS jobs_url_mode ON jobs(url,mode,platform,entry_index);
        CREATE INDEX IF NOT EXISTS files_job ON files(job_id);
        """)
        for k, v in DEFAULTS.items():
            c.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, json.dumps(v)))

        from .config import DESKTOP

        if (
            DESKTOP
            and not c.execute(
                "SELECT 1 FROM migrations WHERE name='permanent-library-v1'"
            ).fetchone()
        ):
            disable_retention(c)
            c.execute("INSERT INTO migrations VALUES ('permanent-library-v1')")


def disable_retention(c):
    c.execute("INSERT OR REPLACE INTO settings VALUES ('retention_days','0')")
    for row in c.execute("SELECT id,settings FROM jobs").fetchall():
        snapshot = json.loads(row["settings"])
        snapshot["retention_days"] = 0
        c.execute(
            "UPDATE jobs SET settings=?,updated_at=? WHERE id=?",
            (json.dumps(snapshot), time.time(), row["id"]),
        )
    c.execute(
        "UPDATE jobs SET expires_at=NULL WHERE status NOT IN ('expired','expiring')"
    )


def expiration(job, now):
    days = job["settings"].get("retention_days", 0)
    return now + days * 86400 if days and settings().get("retention_days", 0) else None


def settings():
    with connect() as c:
        return {
            r["key"]: json.loads(r["value"])
            for r in c.execute("SELECT * FROM settings")
        }


def decode(row):
    if row is None:
        return None
    item = dict(row)
    for key in ("options", "settings", "metadata"):
        item[key] = json.loads(item[key])
    return item


def get(job_id):
    with connect() as c:
        row = decode(c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
        if row:
            row["files"] = [
                dict(r)
                for r in c.execute(
                    "SELECT id,name,size,mime FROM files WHERE job_id=?", (job_id,)
                )
            ]
        return row


def insert(
    c,
    *,
    url,
    platform,
    batch_id,
    mode="video",
    options=None,
    snapshot=None,
    parent_id=None,
    entry_index=None,
    status="queued_metadata",
):
    job_id = uuid.uuid4().hex
    now = time.time()
    c.execute(
        """INSERT INTO jobs (id,batch_id,url,platform,status,mode,options,settings,parent_id,entry_index,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            job_id,
            batch_id,
            url,
            platform,
            status,
            mode,
            json.dumps(options or {}),
            json.dumps(snapshot or DEFAULTS),
            parent_id,
            entry_index,
            now,
            now,
        ),
    )
    return job_id


def update(job_id, **values):
    values["updated_at"] = time.time()
    for key in ("metadata", "options", "settings"):
        if key in values:
            values[key] = json.dumps(values[key], ensure_ascii=False)
    with connect() as c:
        c.execute(
            "UPDATE jobs SET " + ",".join(k + "=?" for k in values) + " WHERE id=?",
            (*values.values(), job_id),
        )


def fail(job_id, code, message, retryable=False):
    update(
        job_id,
        status="failed",
        error_code=code,
        error_message=message,
        retryable=int(retryable),
        progress=0,
    )
