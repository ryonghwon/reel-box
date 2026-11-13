import time

from . import db


def list_jobs(since: float = 0):
    with db.connect() as c:
        c.execute("BEGIN")
        server_time = time.time()
        jobs = [
            db.decode(r)
            for r in c.execute(
                "SELECT * FROM jobs WHERE updated_at>=? ORDER BY created_at DESC",
                (max(0, since),),
            )
        ]
        all_ids = [r[0] for r in c.execute("SELECT id FROM jobs")] if since else None
        files = {}
        for row in c.execute(
            "SELECT f.id,f.job_id,f.name,f.size,f.mime FROM files f JOIN jobs j ON j.id=f.job_id WHERE j.updated_at>=?",
            (max(0, since),),
        ):
            files.setdefault(row["job_id"], []).append(dict(row))
    for j in jobs:
        j["files"] = files.get(j["id"], [])
        j.pop("queue_id", None)
    return {"jobs": jobs, "server_time": server_time, "all_ids": all_ids}
