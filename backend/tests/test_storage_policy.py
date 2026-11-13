import io
import json
import time
import zipfile

import pytest
from app import db, storage, tasks
from app.routes import settings as settings_api


def completed(client, url, snapshot=None):
    jid = client.post("/api/jobs", json={"urls": [url]}).json()["added"][0]
    if snapshot is not None:
        db.update(jid, settings=snapshot)
    job = db.get(jid)
    path = storage.directory(job) / "sample.mp4"
    path.write_bytes(b"preserve-original-media")
    tasks.finish(job, path, {"title": "sample", "media_type": "video"})
    return db.get(jid), path


def test_permanent_files_download_and_zip(client):
    job, path = completed(client, "https://www.instagram.com/p/ABCD1234/")
    assert job["expires_at"] is None
    assert (
        client.get("/api/files/" + job["files"][0]["id"]).content == path.read_bytes()
    )
    choice = client.post("/api/exports", json={"ids": [job["id"]]}).json()["selection"]
    response = client.get("/api/archive.zip?selection=" + choice)
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert any(z.read(n) == path.read_bytes() for n in z.namelist())


def test_disable_retention_protects_existing_and_inflight(client):
    preferences = {**db.DEFAULTS, "retention_days": 7}
    client.put("/api/settings", json=preferences)
    job, path = completed(client, "https://www.instagram.com/p/ABCD1234/")
    assert job["expires_at"] > time.time()
    response = client.put("/api/settings", json={**preferences, "retention_days": 0})
    assert response.status_code == 200 and db.get(job["id"])["expires_at"] is None
    assert (
        db.expiration(job, time.time()) is None
    )  # an already-running worker holds the old snapshot
    assert path.read_bytes() == b"preserve-original-media"
    client.put("/api/settings", json=preferences)
    assert (
        db.get(job["id"])["expires_at"] is None
    )  # reenabling must not retroactively erase old media


def test_custom_location_keeps_old_files_and_limits_paths(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings_api, "DESKTOP", True)
    monkeypatch.setattr(storage, "DESKTOP", True)
    old, oldpath = completed(client, "https://www.instagram.com/p/ABCD1234/")
    destination = tmp_path / "chosen"
    destination.mkdir()
    result = client.post("/api/storage/location", json={"path": str(destination)})
    assert result.status_code == 200, result.text
    assert result.json()["download_directory"] == str(destination)
    new, newpath = completed(client, "https://www.instagram.com/p/EFGH5678/")
    assert newpath.parent.parent == destination
    assert storage.job_path(db.get(old["id"])) == oldpath.parent
    assert (
        client.get("/api/files/" + old["files"][0]["id"]).content
        == oldpath.read_bytes()
    )
    assert (
        client.get("/api/files/" + new["files"][0]["id"]).content
        == newpath.read_bytes()
    )
    assert storage.safe_path(newpath) == newpath
    with pytest.raises(ValueError):
        storage.safe_path(tmp_path / "unselected-file")
    escape = destination / "escape"
    escape.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        storage.safe_path(escape / "unselected-file")
    # Missing removable storage must fail instead of recreating its mount point.
    with db.connect() as c:
        c.execute("DELETE FROM files WHERE job_id=?", (new["id"],))
    newpath.unlink()
    newpath.parent.rmdir()
    escape.unlink()
    destination.rmdir()
    with pytest.raises(OSError, match="STORAGE_UNAVAILABLE"):
        storage.directory(db.get(new["id"]))
    assert not destination.exists() and oldpath.is_file()


def test_desktop_migration_once_preserves_records_and_files(client, monkeypatch):
    from app import config

    old = {**db.DEFAULTS, "retention_days": 7}
    client.put("/api/settings", json=old)
    job, path = completed(client, "https://www.instagram.com/p/ABCD1234/")
    monkeypatch.setattr(config, "DESKTOP", True)
    with db.connect() as c:
        c.execute("DELETE FROM migrations WHERE name='permanent-library-v1'")
    db.init()
    assert (
        db.settings()["retention_days"] == 0 and db.get(job["id"])["expires_at"] is None
    )
    assert path.read_bytes() == b"preserve-original-media"
    client.put("/api/settings", json=old)
    db.init()
    assert (
        db.settings()["retention_days"] == 7
    )  # subsequent user preference survives restart


def test_custom_folder_not_available_from_web_server(client, tmp_path):
    assert (
        client.post("/api/storage/location", json={"path": str(tmp_path)}).status_code
        == 403
    )
