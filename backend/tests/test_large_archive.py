import asyncio
import io
import time
import zipfile
from pathlib import Path
from app import db, storage
from app.routes.exports import archive
from app.config import ROOT


def test_large_zip_survives_source_removal_and_opens_one_file_at_a_time(
    client, monkeypatch
):
    jid = client.post(
        "/api/jobs", json={"urls": ["https://www.instagram.com/p/LargeArchive/"]}
    ).json()["added"][0]
    directory = storage.directory(db.get(jid))
    with db.connect() as connection:
        for index in range(1200):
            path = directory / f"{index}.jpg"
            path.write_bytes(b"archive-fixture")
            connection.execute(
                "INSERT INTO files (id,job_id,name,path,mime,size) VALUES (?,?,?,?,?,?)",
                (
                    f"archive-{index}",
                    jid,
                    path.name,
                    str(path),
                    "image/jpeg",
                    path.stat().st_size,
                ),
            )
    db.update(jid, status="completed", expires_at=time.time() + 3600)
    response = archive(ids=jid)
    storage.purge_partial(db.get(jid))
    original_open = Path.open
    active = 0
    peak = 0

    class Tracked:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self.handle

        def __exit__(self, *args):
            nonlocal active
            self.handle.close()
            active -= 1

    def tracked_open(path, *args, **kwargs):
        nonlocal active, peak
        handle = original_open(path, *args, **kwargs)
        if ".reelbox-export-" not in str(path):
            return handle
        active += 1
        peak = max(peak, active)
        return Tracked(handle)

    monkeypatch.setattr(Path, "open", tracked_open)

    async def consume():
        return b"".join([chunk async for chunk in response.body_iterator])

    contents = asyncio.run(consume())
    with zipfile.ZipFile(io.BytesIO(contents)) as zipped:
        assert len(zipped.namelist()) == 1201
        assert zipped.testzip() is None
        assert zipped.read("1199.jpg") == b"archive-fixture"
    assert peak == 1 and active == 0
    assert not list(ROOT.glob(".reelbox-export-*"))
