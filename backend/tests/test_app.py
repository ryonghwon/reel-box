import io
import json
import socket
import subprocess
import time
import zipfile
from pathlib import Path
import pytest
from app import db, extractor, storage, tasks
from app.urls import normalize, assert_public_url
from app.errors import classify

IG = "https://www.instagram.com/p/SamplePost01/"
META = {
    "id": "abc",
    "title": "테스트 영상",
    "formats": [
        {
            "url": "https://example.com/video.mp4",
            "format_id": "best",
            "protocol": "https",
            "ext": "mp4",
            "vcodec": "h264",
            "acodec": "aac",
            "height": 1080,
        }
    ],
}


def add(client, urls=None, **kwargs):
    r = client.post("/api/jobs", json={"urls": urls or [IG], **kwargs})
    assert r.status_code == 200, r.text
    return r.json()["added"]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a",
        "file:///etc/passwd",
        "https://instagram.com.evil.com/p/abc",
        "https://user:pass@instagram.com/p/a",
        "https://www.instagram.com:9000/p/a",
        "https://www.instagram.com/someuser/",
        "https://www.youtube.com/playlist?list=PLabc",
        "https://www.tiktok.com/@x",
    ],
)
def test_reject_urls(url):
    with pytest.raises(ValueError):
        normalize(url)


def test_canonical_dedup(client):
    r = client.post(
        "/api/jobs",
        json={
            "urls": [
                IG + "?mdxt=tracking",
                IG.replace("/p/", "/reel/"),
                "https://evil.com/foo",
            ]
        },
    ).json()
    assert (
        len(r["added"]) == 1 and len(r["duplicates"]) == 1 and len(r["rejected"]) == 1
    )
    assert not add(client)
    assert len(add(client, mode="audio")) == 1


def test_youtube_collections():
    assert (
        normalize("https://youtu.be/YE7VzlLtp-4?t=10")[0]
        == "https://www.youtube.com/watch?v=YE7VzlLtp-4"
    )
    assert normalize("https://www.youtube.com/watch?v=YE7VzlLtp-4&list=PLabc", True)[
        0
    ].endswith("v=YE7VzlLtp-4")
    assert normalize("https://youtube.com/@Blender", True)[0].endswith(
        "/@Blender/videos"
    )
    assert normalize("https://youtube.com/playlist?list=PLabc", True)[0].endswith(
        "list=PLabc"
    )


def test_secret_and_settings(client):
    assert client.get("/api/jobs", headers={"X-API-Key": "wrong"}).status_code == 401
    for patch in [
        {"folder": "../etc"},
        {"filename_template": "{title.__class__}"},
        {"filename_template": "{title:1000000}"},
        {"retention_days": -1},
    ]:
        assert (
            client.put("/api/settings", json={**db.DEFAULTS, **patch}).status_code
            == 422
        )
    assert (
        client.put(
            "/api/settings",
            json={**db.DEFAULTS, "folder": "내 영상", "retention_days": 3},
        ).status_code
        == 200
    )
    jid = add(client)[0]
    client.put("/api/settings", json={**db.DEFAULTS, "retention_days": 7})
    assert db.get(jid)["settings"]["retention_days"] == 3


def test_public_address_guard(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))]
    )
    with pytest.raises(ValueError):
        assert_public_url("https://www.instagram.com/p/a")
    with pytest.raises(ValueError):
        assert_public_url("file:///etc/passwd")


@pytest.mark.parametrize(
    "text,code",
    [
        ("DRM protected", "DRM_PROTECTED"),
        ("login required", "AUTH_REQUIRED"),
        ("HTTP Error 429", "RATE_LIMITED"),
        ("HTTP Error 403", "ACCESS_RESTRICTED"),
        ("Unsupported URL", "EXTRACTOR_UNSUPPORTED"),
        ("Connection timed out", "NETWORK_ERROR"),
        ("No video formats", "NO_MEDIA"),
        ("DISK_FULL", "DISK_FULL"),
    ],
)
def test_error_categories(text, code):
    assert classify(ValueError(text))[0] == code


def test_metadata_download_zip_csv_and_retry(client, monkeypatch, tmp_path):
    jid = add(client)[0]
    monkeypatch.setattr(extractor, "extract", lambda j: dict(META))
    tasks.run(jid, "metadata", 0)
    assert db.get(jid)["status"] == "ready"
    assert db.get(jid)["metadata"]["max_height"] == 1080
    assert client.post("/api/jobs/start", json={"ids": [jid]}).json()["updated"] == [
        jid
    ]
    assert client.post("/api/jobs/start", json={"ids": [jid]}).json()["updated"] == []

    def fail(*a):
        raise TimeoutError("Connection timed out")

    monkeypatch.setattr(extractor, "download", fail)
    tasks.run(jid, "download", 1)
    assert db.get(jid)["error_code"] == "NETWORK_ERROR"
    assert client.post("/api/jobs/retry", json={"ids": [jid]}).json()["updated"] == [
        jid
    ]

    def fetch(job, target, stem, progress):
        path = target / (stem + ".mp4")
        path.write_bytes(b"fake-media-in-unit-test")
        progress(92)
        return path, {"title": '=HYPERLINK("evil")', "id": "abc"}

    monkeypatch.setattr(extractor, "download", fetch)
    tasks.run(jid, "download", 2)
    job = db.get(jid)
    assert job["status"] == "completed"
    assert len(job["files"]) == 1
    assert (
        client.get("/api/files/" + job["files"][0]["id"]).content
        == b"fake-media-in-unit-test"
    )
    output = client.get("/api/archive.zip?ids=" + jid)
    archive = zipfile.ZipFile(io.BytesIO(output.content))
    assert len(archive.namelist()) == 2
    manifest = archive.read("manifest.csv").decode("utf-8-sig")
    assert "'=HYPERLINK" in manifest
    assert IG in manifest
    tasks.run(jid, "download", 2)
    assert len(db.get(jid)["files"]) == 1
    db.update(jid, expires_at=time.time() - 1)
    assert client.get("/api/files/" + job["files"][0]["id"]).status_code == 404


def test_carousel_expands_and_child_selection(client, monkeypatch):
    jid = add(client)[0]
    monkeypatch.setattr(
        extractor,
        "extract",
        lambda j: {
            "_type": "playlist",
            "id": "post",
            "entries": [dict(META), dict(META, id="second")],
        },
    )
    tasks.run(jid, "metadata", 0)
    jobs = client.get("/api/jobs").json()["jobs"]
    assert len(jobs) == 3
    assert db.get(jid)["status"] == "expanded"
    assert sorted(j["entry_index"] for j in jobs if j["parent_id"]) == [0, 1]


def test_playlist_bounded_and_duplicate_children(client, monkeypatch):
    root = "https://www.youtube.com/playlist?list=PLabc"
    jid = add(client, [root], collections=True, collection_limit=2)[0]
    monkeypatch.setattr(
        extractor,
        "extract",
        lambda j: {
            "_type": "playlist",
            "id": "pl",
            "entries": [
                {"url": "https://www.youtube.com/watch?v=YE7VzlLtp-4"},
                {"url": "https://www.youtube.com/watch?v=YE7VzlLtp-4"},
                {"url": "https://www.youtube.com/watch?v=BaW_jenozKc"},
            ],
        },
    )
    tasks.run(jid, "metadata", 0)
    assert len(client.get("/api/jobs").json()["jobs"]) == 2
    assert "일부" in db.get(jid)["note"]


def test_drm_and_live_rejected():
    with pytest.raises(ValueError, match="DRM"):
        extractor.verify_media({"has_drm": True}, "video")
    with pytest.raises(ValueError, match="LIVE"):
        extractor.verify_media({"is_live": True}, "video")


def test_recording_to_real_mp4(client, tmp_path):
    source = tmp_path / "fixture.webm"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=12",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "1",
            "-c:v",
            "libvpx",
            "-c:a",
            "libopus",
            str(source),
        ],
        check=True,
    )
    r = client.post(
        "/api/recordings?title=screen-test&source=" + IG,
        content=source.read_bytes(),
        headers={"Content-Type": "video/webm"},
    )
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    job = db.get(jid)
    assert job["status"] == "queued_download"
    tasks.run(jid, "download", 0)
    job = db.get(jid)
    assert job["status"] == "completed", job
    assert job["files"][0]["name"].endswith(".mp4")
    saved = tmp_path / "result.mp4"
    saved.write_bytes(client.get("/api/files/" + job["files"][0]["id"]).content)
    probe = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(saved)]
        )
    )
    assert {s["codec_name"] for s in probe["streams"]} == {"h264", "aac"}


def test_invalid_upload(client):
    r = client.post(
        "/api/recordings", content=b"bad-media", headers={"Content-Type": "video/webm"}
    )
    assert r.status_code == 422
    assert client.get("/api/jobs").json()["jobs"][0]["status"] == "failed"


def test_concurrent_start(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    jid = add(client)[0]
    db.update(jid, status="ready")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: client.post("/api/jobs/start", json={"ids": [jid]}).json(),
                range(4),
            )
        )
    assert sum(len(r["updated"]) for r in results) == 1
    assert db.get(jid)["attempt"] == 1


def test_convert_rejects_incomplete(client):
    jid = add(client)[0]
    assert client.post(f"/api/jobs/{jid}/compatible").status_code == 409


def test_large_export_selection_uses_short_token(client):
    jid = add(client)[0]
    token = client.post("/api/exports", json={"ids": [jid] + ["f" * 32] * 1999}).json()[
        "selection"
    ]
    assert len(token) == 32
    r = client.get("/api/manifest.csv?selection=" + token)
    assert r.status_code == 200 and IG in r.text
    with db.connect() as c:
        c.execute("UPDATE exports SET expires_at=0 WHERE id=?", (token,))
    assert client.get("/api/manifest.csv?selection=" + token).status_code == 410
