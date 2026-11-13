import json
import os
import subprocess
import time
import pytest
from app import db, extractor, tasks
from app.desktop_queue import LocalQueue

IG = "https://www.instagram.com/p/SamplePost01/"


def test_vimeo_client_login_error_explains_missing_integration():
    from app.errors import classify

    code, message, retryable = classify(
        "ERROR: [vimeo] 1234567890: The web client only works when logged-in. Use cookies to provide account credentials."
    )
    assert code == "AUTH_REQUIRED" and not retryable
    assert "브라우저 로그인만으로 해결되지 않습니다" in message


def test_mp4_default_and_actual_quality_choices(client, monkeypatch):
    jid = client.post("/api/jobs", json={"urls": [IG]}).json()["added"][0]
    assert db.get(jid)["options"]["output_format"] == "mp4"
    meta = {
        "id": "a",
        "formats": [
            {"protocol": "https", "height": 2160, "vcodec": "vp9", "acodec": "none"},
            {"protocol": "https", "height": 1080, "vcodec": "h264", "acodec": "aac"},
            {"protocol": "https", "vcodec": "none", "acodec": "aac"},
        ],
    }
    monkeypatch.setattr(extractor, "extract", lambda j: meta)
    tasks.run(jid, "metadata", 0)
    assert db.get(jid)["metadata"]["available_heights"] == [2160, 1080]
    assert (
        client.put(f"/api/jobs/{jid}/preferences", json={"height": 720}).status_code
        == 422
    )
    result = client.put(
        f"/api/jobs/{jid}/preferences", json={"height": 1080, "output_format": "mp4"}
    )
    assert result.status_code == 200 and db.get(jid)["options"]["height"] == 1080
    client.post("/api/jobs/start", json={"ids": [jid]})
    assert (
        client.put(f"/api/jobs/{jid}/preferences", json={"height": 2160}).status_code
        == 409
    )


def test_mp4_conversion_keeps_high_resolution(tmp_path):
    path = tmp_path / "source.webm"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:size=1280x960:rate=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "1",
            "-c:v",
            "libvpx-vp9",
            "-c:a",
            "libopus",
            str(path),
        ],
        check=True,
    )
    output = extractor.ensure_mp4(path)
    assert output.suffix == ".mp4" and not path.exists()
    meta = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)]
        )
    )
    video = next(s for s in meta["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"], video["codec_name"]) == (1280, 960, "h264")
    assert (
        next(s for s in meta["streams"] if s["codec_type"] == "audio")["codec_name"]
        == "aac"
    )
    before = output.read_bytes()
    assert extractor.ensure_mp4(output).read_bytes() == before


def test_desktop_queue_restarts_interrupted_and_handles_real_subprocess(
    client, tmp_path
):
    # This app-created recording fixture requires neither Redis nor any external website.
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
            "color=c=green:size=320x240:rate=4",
            "-t",
            "1",
            "-c:v",
            "libvpx",
            str(source),
        ],
        check=True,
    )
    response = client.post(
        "/api/recordings?title=native-queue-test",
        content=source.read_bytes(),
        headers={"Content-Type": "video/webm"},
    )
    assert response.status_code == 200, response.text
    jid = response.json()["id"]
    db.update(jid, status="downloading")
    runner = LocalQueue()
    runner.recover()
    assert db.get(jid)["status"] == "queued_download" and db.get(jid)["attempt"] == 1
    # Child must see the same isolated paths chosen by conftest.
    runner.start()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and db.get(jid)["status"] not in (
            "completed",
            "failed",
        ):
            time.sleep(0.2)
        assert db.get(jid)["status"] == "completed", db.get(jid)
        assert db.get(jid)["files"][0]["name"].endswith(".mp4")
    finally:
        runner.stop()
    assert not runner.alive
    db.update(jid, expires_at=time.time() - 1)
    runner.expire()
    assert db.get(jid)["status"] == "expired"


def test_platform_cooldown_requeues_failures_preserves_files_and_backs_off(
    client, monkeypatch
):
    import app.desktop_queue as queue_module

    now = [1000.0]
    monkeypatch.setattr(queue_module.time, "time", lambda: now[0])
    with db.connect() as c:
        a = db.insert(c, url=IG, platform="instagram", batch_id="a", status="failed")
        b = db.insert(
            c, url=IG, platform="instagram", batch_id="b", status="queued_metadata"
        )
        done = db.insert(
            c, url=IG, platform="instagram", batch_id="d", status="completed"
        )
        c.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?)",
            ("f", done, "/keep", "keep", 123, "video/mp4"),
        )
    db.fail(a, "RATE_LIMITED", "HTTP 429", True)
    runner = LocalQueue()
    runner.defer_rate_limited()
    assert db.get(a)["status"] == "queued_metadata" and db.get(a)["attempt"] == 1
    with db.connect() as c:
        assert c.execute("SELECT until FROM platform_cooldowns").fetchone()[0] == 1300
    now[0] = 1050
    db.fail(b, "RATE_LIMITED", "HTTP 429", True)
    runner.defer_rate_limited()
    with db.connect() as c:
        assert c.execute("SELECT until FROM platform_cooldowns").fetchone()[0] == 1300
    now[0] = 1301
    db.fail(a, "RATE_LIMITED", "HTTP 429", True)
    runner.defer_rate_limited()
    with db.connect() as c:
        assert c.execute("SELECT until FROM platform_cooldowns").fetchone()[0] == 1901
    assert (
        db.get(done)["status"] == "completed" and db.get(done)["files"][0]["id"] == "f"
    )


def test_numeric_media_id_is_not_a_rate_limit():
    from app.errors import classify

    assert classify("Cannot extract media id 178429123456")[0] != "RATE_LIMITED"
    assert classify("HTTP Error 429: Too Many Requests")[0] == "RATE_LIMITED"
