"""A persisted, single-user desktop queue. Redis/RQ remains the server option."""

import os
import signal
import subprocess
import sys
import threading
import time

from . import db, storage
from .config import WORKERS


def terminate_tree(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=15,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


class LocalQueue:
    def __init__(self):
        self.stopping = threading.Event()
        self.thread = None
        self.running = {}

    @property
    def alive(self):
        return bool(
            self.thread and self.thread.is_alive() and not self.stopping.is_set()
        )

    def recover(self):
        with db.connect() as c:
            rows = [
                db.decode(r)
                for r in c.execute(
                    "SELECT * FROM jobs WHERE status IN ('extracting','downloading','recording')"
                )
            ]
        for row in rows:
            if row["status"] == "recording":
                db.fail(
                    row["id"],
                    "UPLOAD_INTERRUPTED",
                    "앱이 종료되어 업로드가 중단되었습니다. 파일을 다시 가져오세요.",
                )
                continue
            if row["platform"] != "recording":
                storage.purge_partial(row)
            db.update(
                row["id"],
                status="queued_" + row["phase"],
                attempt=row["attempt"] + 1,
                progress=0,
            )

    def start(self):
        self.recover()
        self.thread = threading.Thread(
            target=self.loop, name="reelbox-queue", daemon=True
        )
        self.thread.start()

    def expire(self):
        with db.connect() as c:
            rows = [
                db.decode(r)
                for r in c.execute(
                    "SELECT * FROM jobs WHERE (status='completed' AND expires_at<?) OR (status='failed' AND platform='recording' AND expires_at<?) OR status='expiring'",
                    (time.time(), time.time()),
                )
            ]
        for row in rows:
            db.update(row["id"], status="expiring")
            try:
                storage.purge_partial(row)
            except PermissionError:
                continue  # Windows may still be streaming this file.
            with db.connect() as c:
                c.execute("DELETE FROM files WHERE job_id=?", (row["id"],))
            db.update(row["id"], status="expired", progress=0)

    def tick(self):
        self.expire()
        for jid, (process, job, started) in list(self.running.items()):
            limit = 300 if job["phase"] == "metadata" else 7200
            if process.poll() is None and time.monotonic() - started > limit:
                terminate_tree(process)
            if process.poll() is None:
                continue
            current = db.get(jid)
            if (
                current
                and current["status"]
                in ("extracting", "downloading", "queued_metadata", "queued_download")
                and current["attempt"] == job["attempt"]
            ):
                if current["platform"] != "recording":
                    storage.purge_partial(current)
                db.fail(
                    current["id"],
                    "WORKER_INTERRUPTED",
                    "작업이 중단되었습니다. 다시 시도할 수 있습니다.",
                    True,
                )
            del self.running[jid]
        self.defer_rate_limited()
        if len(self.running) >= WORKERS:
            return
        with db.connect() as c:
            rows = [
                db.decode(r)
                for r in c.execute(
                    "SELECT * FROM jobs WHERE status IN ('queued_metadata','queued_download') AND platform NOT IN (SELECT platform FROM platform_cooldowns WHERE until>?) ORDER BY CASE WHEN status='queued_download' THEN 0 ELSE 1 END,created_at LIMIT ?",
                    (time.time(), WORKERS * 2),
                )
            ]
        for row in rows:
            if len(self.running) >= WORKERS:
                break
            if row["id"] in self.running:
                continue
            opts = (
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "app.desktop_worker",
                    row["id"],
                    row["phase"],
                    str(row["attempt"]),
                ],
                stdin=subprocess.DEVNULL,
                **opts,
            )
            self.running[row["id"]] = (process, row, time.monotonic())

    def defer_rate_limited(self):
        now = time.time()
        with db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            platforms = [
                r[0]
                for r in c.execute(
                    "SELECT DISTINCT platform FROM jobs WHERE status='failed' AND error_code='RATE_LIMITED'"
                )
            ]
            for platform in platforms:
                old = c.execute(
                    "SELECT until,strikes FROM platform_cooldowns WHERE platform=?",
                    (platform,),
                ).fetchone()
                # In-flight requests may finish after the first limit response.
                # They join the same cooldown instead of extending it each tick.
                strikes = (
                    old["strikes"]
                    if old and old["until"] > now
                    else (old["strikes"] + 1 if old else 1)
                )
                until = (
                    old["until"]
                    if old and old["until"] > now
                    else now + min(3600, 300 * 2 ** min(strikes - 1, 4))
                )
                c.execute(
                    "INSERT OR REPLACE INTO platform_cooldowns VALUES (?,?,?)",
                    (platform, until, strikes),
                )
                message = (
                    "플랫폼 요청 제한 · "
                    + time.strftime("%H:%M", time.localtime(until))
                    + " 이후 자동 재개"
                )
                c.execute(
                    "UPDATE jobs SET status='queued_'||phase,attempt=attempt+1,progress=0,error_code=NULL,error_message=NULL,retryable=0,updated_at=? WHERE platform=? AND status='failed' AND error_code='RATE_LIMITED'",
                    (now, platform),
                )
                c.execute(
                    "UPDATE jobs SET note=?,updated_at=? WHERE platform=? AND status IN ('queued_metadata','queued_download')",
                    (message, now, platform),
                )

    def loop(self):
        while not self.stopping.is_set():
            try:
                self.tick()
            except Exception:
                import logging

                logging.exception("Desktop queue error")
            self.stopping.wait(1)

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=20)
        for process, _, _ in self.running.values():
            terminate_tree(process)
        self.running.clear()
        # Persisted queued/in-progress states are recovered on the next launch.
