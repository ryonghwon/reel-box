"""Attach browser saves to their existing library records without deleting media."""

import json
import time
from collections import Counter
from . import db


def merge_failed(c, saved_id, target_id="", post_index=None):
    saved = db.decode(
        c.execute("SELECT * FROM jobs WHERE id=?", (saved_id,)).fetchone()
    )
    if not saved or saved["status"] != "completed":
        return None
    if target_id:
        targets = [
            db.decode(
                c.execute("SELECT * FROM jobs WHERE id=?", (target_id,)).fetchone()
            )
        ]
    else:
        targets = [
            db.decode(r)
            for r in c.execute(
                "SELECT * FROM jobs WHERE url=? AND platform=? AND mode=? AND status='failed' AND parent_id IS NULL",
                (saved["url"], saved["platform"], saved["mode"]),
            )
        ]
        if len(targets) != 1:
            return None
    target = targets[0]
    if not target or target["id"] == saved_id or target["status"] != "failed":
        return None
    if (target["url"], target["platform"], target["mode"]) != (
        saved["url"],
        saved["platform"],
        saved["mode"],
    ):
        return None
    if target["parent_id"] and (
        post_index is None or target["entry_index"] != post_index
    ):
        return None
    if saved["parent_id"] and (saved["parent_id"], saved["entry_index"]) != (
        target["parent_id"],
        target["entry_index"],
    ):
        return None
    if c.execute("SELECT 1 FROM files WHERE job_id=?", (target["id"],)).fetchone():
        return None
    if c.execute("SELECT 1 FROM jobs WHERE parent_id=?", (target["id"],)).fetchone():
        return None
    # Keep the failed record in the completed record's history. The successful
    # record keeps its ID and directory, so no downloaded file is moved/deleted.
    options = {
        **target["options"],
        **saved["options"],
        "source": target["options"].get(
            "source", saved["options"].get("source", "browser")
        ),
        "browser_import": True,
    }
    history = list(options.get("browser_replaced_records", []))
    history.append(
        {
            k: target[k]
            for k in (
                "id",
                "error_code",
                "error_message",
                "created_at",
                "parent_id",
                "entry_index",
            )
        }
    )
    options["browser_replaced_records"] = history
    metadata = {**target["metadata"], **saved["metadata"]}
    for key in ("title", "uploader", "webpage_url"):
        if not saved["metadata"].get(key) and target["metadata"].get(key):
            metadata[key] = target["metadata"][key]
    metadata["webpage_url"] = saved["url"]
    if metadata.get("title", "").lower() == "instagram":
        metadata["title"] = (
            metadata.get("id") or saved["url"].rstrip("/").split("/")[-1]
        )
    if target["parent_id"] and target["metadata"].get("id"):
        metadata["id"] = target["metadata"]["id"]
    c.execute("DELETE FROM jobs WHERE id=?", (target["id"],))
    c.execute(
        "UPDATE jobs SET batch_id=?,parent_id=?,entry_index=?,created_at=?,metadata=?,options=?,error_code=NULL,error_message=NULL,retryable=0,updated_at=? WHERE id=?",
        (
            target["batch_id"],
            target["parent_id"],
            target["entry_index"],
            target["created_at"],
            json.dumps(metadata, ensure_ascii=False),
            json.dumps(options, ensure_ascii=False),
            time.time(),
            saved_id,
        ),
    )
    return target["id"]


def reconcile_existing():
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        rows = c.execute(
            "SELECT id,url FROM jobs WHERE status='completed' AND (json_extract(options,'$.source')='browser' OR json_extract(options,'$.browser_import')=1)"
        ).fetchall()
        counts = Counter(row["url"] for row in rows)
        for row in rows:
            # Automatic legacy reconciliation is only unambiguous for one
            # completed browser item and one failed root with no child records.
            if counts[row["url"]] == 1:
                merge_failed(c, row["id"])
        for row in rows:
            job = db.decode(
                c.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            )
            meta = job["metadata"]
            meta["webpage_url"] = job["url"]
            if not meta.get("title") or meta["title"].strip().lower() == "instagram":
                meta["title"] = job["url"].rstrip("/").split("/")[-1]
            c.execute(
                "UPDATE jobs SET metadata=?,updated_at=? WHERE id=?",
                (json.dumps(meta, ensure_ascii=False), time.time(), job["id"]),
            )
