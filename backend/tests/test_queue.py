import os
import time
import pytest
from redis import Redis
from rq import Queue, SimpleWorker
from rq.job import Job, JobStatus
from app import db, extractor, maintenance, storage, tasks
from app.main import list_jobs

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_REDIS_URL"),
    reason="Set TEST_REDIS_URL to a dedicated disposable Redis database",
)


@pytest.fixture
def redis(monkeypatch):
    url = os.environ["TEST_REDIS_URL"]
    r = Redis.from_url(url)
    assert url.endswith("/15"), "Tests are restricted to isolated database 15"
    r.flushdb()
    monkeypatch.setattr(maintenance, "REDIS_URL", url)
    yield r
    r.flushdb()


def test_redis_dispatch_recovery_and_retention(client, redis, monkeypatch):
    jid = client.post(
        "/api/jobs", json={"urls": ["https://www.instagram.com/p/SamplePost01/"]}
    ).json()["added"][0]
    monkeypatch.setattr(
        extractor,
        "extract",
        lambda j: {
            "id": "test",
            "title": "test",
            "formats": [{"protocol": "https", "vcodec": "h264", "acodec": "aac"}],
        },
    )
    maintenance.tick()
    maintenance.tick()
    queue = Queue("metadata", connection=redis)
    assert queue.count == 1
    SimpleWorker([queue], connection=redis).work(burst=True)
    assert db.get(jid)["status"] == "ready"
    client.post("/api/jobs/start", json={"ids": [jid]})
    maintenance.tick()
    queued = Job.fetch(f"{jid}-download-1", connection=redis)
    queued.set_status(JobStatus.FAILED)
    db.update(jid, status="downloading")
    maintenance.tick()
    assert db.get(jid)["error_code"] == "WORKER_INTERRUPTED"
    path = storage.directory(db.get(jid)) / "test.mp4"
    path.write_bytes(b"test")
    tasks.finish(db.get(jid), path, {"title": "test"})
    db.update(jid, expires_at=time.time() - 1)
    maintenance.tick()
    assert db.get(jid)["status"] == "expired"
    assert db.get(jid)["metadata"]["title"] == "test"
    assert not path.exists()


def test_saved_auto_download_survives_metadata_queue_completion(
    client, redis, monkeypatch
):
    jid = client.post(
        "/api/jobs",
        json={
            "urls": ["https://www.instagram.com/p/SamplePost01/"],
            "auto_download": True,
            "source": "instagram_saved",
        },
    ).json()["added"][0]
    monkeypatch.setattr(
        extractor,
        "extract",
        lambda j: {
            "id": "test",
            "title": "test",
            "formats": [{"protocol": "https", "vcodec": "h264", "acodec": "aac"}],
        },
    )

    def download(job, target, stem, progress):
        path = target / (stem + ".mp4")
        path.write_bytes(b"isolated-unit-fixture")
        return path, {"title": "auto"}

    monkeypatch.setattr(extractor, "download", download)
    queue = Queue("metadata", connection=redis)
    maintenance.tick()
    SimpleWorker([queue], connection=redis).work(burst=True)
    assert db.get(jid)["status"] == "queued_download"
    maintenance.tick()
    maintenance.tick()
    queue = Queue("downloads", connection=redis)
    assert queue.count == 1
    SimpleWorker([queue], connection=redis).work(burst=True)
    maintenance.tick()
    assert db.get(jid)["status"] == "completed"
    assert len(db.get(jid)["files"]) == 1
