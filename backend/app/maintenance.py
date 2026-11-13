import logging
import time
from redis import Redis
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError
from . import db, storage
from .config import REDIS_URL


def tick():
    redis = Redis.from_url(REDIS_URL, socket_connect_timeout=3, socket_timeout=3)
    queues = {
        phase: Queue(name, connection=redis)
        for phase, name in [("metadata", "metadata"), ("download", "downloads")]
    }
    with db.connect() as c:
        rows = [
            db.decode(r)
            for r in c.execute(
                "SELECT * FROM jobs WHERE status IN ('queued_metadata','queued_download','extracting','downloading','recording')"
            )
        ]
    for row in rows:
        if row["status"] == "recording":
            if (
                time.time() - row["updated_at"] > 120
            ):  # upload heartbeats update this timestamp
                storage.purge_partial(row)
                db.fail(
                    row["id"],
                    "UPLOAD_INTERRUPTED",
                    "녹화 파일 업로드가 중단되었습니다. 파일을 다시 저장하세요.",
                )
            continue
        queue_id = f"{row['id']}-{row['phase']}-{row['attempt']}"
        try:
            rqjob = Job.fetch(queue_id, connection=redis)
            state = rqjob.get_status(refresh=True).value
            if state in ("failed", "stopped", "canceled", "finished"):
                # Recheck current DB state; completion may race with this snapshot.
                current = db.get(row["id"])
                if (
                    current
                    and current["status"]
                    in (
                        "extracting",
                        "downloading",
                        "queued_metadata",
                        "queued_download",
                    )
                    and current["attempt"] == row["attempt"]
                ):
                    if row["platform"] != "recording":
                        storage.purge_partial(row)
                    db.fail(
                        row["id"],
                        "WORKER_INTERRUPTED",
                        "작업이 중단되거나 제한 시간을 초과했습니다. 다시 시도하세요.",
                        True,
                    )
        except NoSuchJobError:
            if row["status"].startswith("queued_"):
                queues[row["phase"]].enqueue(
                    "app.tasks.run",
                    row["id"],
                    row["phase"],
                    row["attempt"],
                    job_id=queue_id,
                    job_timeout=300 if row["phase"] == "metadata" else 7200,
                    result_ttl=86400,
                    failure_ttl=604800,
                )
                db.update(row["id"], queue_id=queue_id)
            else:
                if row["platform"] != "recording":
                    storage.purge_partial(row)
                db.fail(
                    row["id"],
                    "WORKER_INTERRUPTED",
                    "작업 정보를 복구하지 못했습니다. 다시 시도하세요.",
                    True,
                )
    # Claim expiration with an atomic state change. Metadata remains in the history.
    with db.connect() as c:
        expired = [
            db.decode(r)
            for r in c.execute(
                "SELECT * FROM jobs WHERE (status='completed' AND expires_at<?) OR (status='failed' AND platform='recording' AND expires_at<?) OR status='expiring'",
                (time.time(), time.time()),
            )
        ]
    for row in expired:
        db.update(row["id"], status="expiring")
        storage.purge_partial(row)
        with db.connect() as c:
            c.execute("DELETE FROM files WHERE job_id=?", (row["id"],))
        db.update(row["id"], status="expired", progress=0)


if __name__ == "__main__":
    db.init()
    while True:
        try:
            tick()
        except Exception:
            logging.exception("maintenance tick failed")
        time.sleep(5)
