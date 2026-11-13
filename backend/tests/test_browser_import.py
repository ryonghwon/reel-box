import importlib
import subprocess
from urllib.parse import urlencode
from app import db, storage
from app.errors import classify

URL = "https://www.instagram.com/p/SamplePost03/"


def test_error_reasons_do_not_confuse_login_hints_with_evidence():
    assert (
        classify("Instagram sent an empty media response. Use --cookies for login")[0]
        == "MEDIA_DATA_UNAVAILABLE"
    )
    assert classify("HTTP 429 login required")[0] == "RATE_LIMITED"
    assert (
        classify(
            "Restricted Video: This content isn't available to everyone. Certain audiences."
        )[0]
        == "AUDIENCE_RESTRICTED"
    )
    assert (
        classify("Please verify your age to watch this age-restricted video")[0]
        == "AGE_RESTRICTED"
    )
    assert classify("DRM age-restricted private video")[0] == "DRM_PROTECTED"


def upload(client, raw, kind="image", source=URL, **extra):
    return client.post(
        "/api/imports/browser-media?"
        + urlencode(
            {"source": source, "title": "직접 선택한 자료", "kind": kind, **extra}
        ),
        content=raw,
    )


def enable(monkeypatch):
    monkeypatch.setattr(importlib.import_module("app.main"), "DESKTOP", True)


def test_browser_import_is_desktop_only_and_keeps_auth(client):
    assert upload(client, b"bad").status_code == 404
    assert (
        client.post(
            "/api/imports/browser-media?source=" + URL,
            content=b"bad",
            headers={"X-API-Key": "wrong"},
        ).status_code
        == 401
    )


def test_explicit_image_import_merges_failed_original_deduplicates_and_expires(
    client, monkeypatch, tmp_path
):
    enable(monkeypatch)
    client.put("/api/settings", json={**db.DEFAULTS, "retention_days": 7})
    original = client.post("/api/jobs", json={"urls": [URL]}).json()["added"][0]
    db.fail(original, "AUTH_REQUIRED", "test")
    p = tmp_path / "image.png"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:size=600x400",
            "-frames:v",
            "1",
            str(p),
        ],
        check=True,
    )
    result = upload(client, p.read_bytes())
    assert result.status_code == 200, result.text
    jid = result.json()["id"]
    j = db.get(jid)
    assert j["status"] == "completed" and j["metadata"]["media_type"] == "image"
    assert j["metadata"]["width"] == 600 and j["metadata"]["height"] == 400
    assert (
        j["url"] == URL
        and j["platform"] == "instagram"
        and j["expires_at"] > j["finished_at"]
    )
    assert (
        j["files"][0]["mime"] == "image/png"
        and client.get("/api/files/" + j["files"][0]["id"]).content == p.read_bytes()
    )
    again = upload(client, p.read_bytes()).json()
    assert again == {"id": jid, "duplicate": True, "merged": None}
    assert db.get(original) is None
    assert j["options"]["browser_replaced_records"][0]["id"] == original
    assert result.json()["merged"] == original
    assert client.get(j["metadata"]["thumbnail"]).status_code == 200


def test_video_import_preserves_resolution_audio_and_generates_preview(
    client, monkeypatch, tmp_path
):
    enable(monkeypatch)
    p = tmp_path / "video.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:size=960x540:rate=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=400",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(p),
        ],
        check=True,
    )
    result = upload(client, p.read_bytes(), "video")
    assert result.status_code == 200, result.text
    j = db.get(result.json()["id"])
    assert j["metadata"]["width"] == 960 and j["metadata"]["height"] == 540
    assert j["files"][0]["mime"] == "video/mp4"
    assert client.get(j["metadata"]["thumbnail"]).status_code == 200
    raw = client.get("/api/files/" + j["files"][0]["id"]).content
    assert raw == p.read_bytes()


def test_bad_and_oversize_imports_leave_no_files(client, monkeypatch):
    enable(monkeypatch)
    assert (
        upload(
            client, b"bad", source="https://youtube.com/watch?v=abcdefghijk"
        ).status_code
        == 400
    )
    bad = upload(client, b"<html>not media</html>")
    assert bad.status_code == 422
    with db.connect() as c:
        row = db.decode(c.execute("SELECT * FROM jobs LIMIT 1").fetchone())
        assert c.execute("SELECT count(*) FROM files").fetchone()[0] == 0
    assert row["status"] == "failed"
    assert not (storage.folder_path(row["settings"]["folder"]) / row["id"]).exists()
    monkeypatch.setattr(importlib.import_module("app.main"), "MAX_BYTES", 8)
    assert upload(client, b"123456789").status_code == 413


def test_carousel_failure_is_kept_until_all_saved_then_grouped(
    client, monkeypatch, tmp_path
):
    enable(monkeypatch)
    original = client.post("/api/jobs", json={"urls": [URL]}).json()["added"][0]
    db.update(original, options={"source": "instagram_saved"})
    db.fail(original, "AUTH_REQUIRED", "test")
    saved = []
    for color in ["red", "blue"]:
        p = tmp_path / (color + ".png")
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:size=600x400",
                "-frames:v",
                "1",
                str(p),
            ],
            check=True,
        )
        r = upload(client, p.read_bytes(), defer_merge="true")
        assert r.status_code == 200, r.text
        saved.append(r.json()["id"])
        assert db.get(original)["status"] == "failed"
    before = [db.get(j)["files"] for j in saved]
    r = client.post(
        "/api/imports/browser-complete-post",
        json={"target_id": original, "saved_ids": saved},
    )
    assert r.status_code == 200 and r.json()["merged"] == original
    assert db.get(original) is None
    assert db.get(saved[0])["options"]["source"] == "instagram_saved"
    assert db.get(saved[1])["parent_id"] == saved[0]
    assert db.get(saved[1])["options"]["source"] == "instagram_saved"
    assert [db.get(j)["files"] for j in saved] == before


def test_browser_metadata_refresh_preserves_files_and_updates_link(
    client, monkeypatch, tmp_path
):
    enable(monkeypatch)
    p = tmp_path / "image.png"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:size=600x400",
            "-frames:v",
            "1",
            str(p),
        ],
        check=True,
    )
    jid = upload(client, p.read_bytes()).json()["id"]
    before = db.get(jid)["files"]
    r = client.post(
        "/api/imports/browser-metadata",
        json={"source": URL, "title": "작품 제목", "uploader": "artist"},
    )
    assert r.status_code == 200
    j = db.get(jid)
    assert (
        j["metadata"]["title"] == "작품 제목" and j["metadata"]["uploader"] == "artist"
    )
    assert j["metadata"]["webpage_url"] == URL and j["files"] == before


def test_merging_is_exact_and_never_deletes_existing_media(client):
    from app.browser_reconcile import merge_failed, reconcile_existing

    with db.connect() as c:
        root = db.insert(
            c, url=URL, platform="instagram", batch_id="root", status="expanded"
        )
        child = db.insert(
            c,
            url=URL,
            platform="instagram",
            batch_id="root",
            parent_id=root,
            entry_index=2,
            status="failed",
        )
        saved = db.insert(
            c,
            url=URL,
            platform="instagram",
            batch_id="saved",
            status="completed",
            options={"source": "browser"},
        )
        assert merge_failed(c, saved, child, 1) is None
        assert merge_failed(c, saved, root) is None
        assert merge_failed(c, saved) is None
        c.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?)",
            ("existing", child, "/example/keep.mp4", "keep.mp4", 123, "video/mp4"),
        )
        assert merge_failed(c, saved, child, 2) is None
        c.execute("DELETE FROM files WHERE id=?", ("existing",))
        assert merge_failed(c, saved, child, 2) == child
    assert db.get(saved)["parent_id"] == root and db.get(saved)["entry_index"] == 2
    assert db.get(child) is None
    reconcile_existing()
    assert db.get(saved)["parent_id"] == root


def test_startup_reconciliation_is_idempotent_and_preserves_file_identity(client):
    from app.browser_reconcile import reconcile_existing

    with db.connect() as c:
        old = db.insert(
            c,
            url=URL,
            platform="instagram",
            batch_id="import",
            status="failed",
            options={"source": "instagram_saved"},
        )
        saved = db.insert(
            c,
            url=URL,
            platform="instagram",
            batch_id="browser",
            status="completed",
            options={"source": "browser"},
        )
        c.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?)",
            ("file", saved, "/example/keep.mp4", "keep.mp4", 123, "video/mp4"),
        )
    before = db.get(saved)["files"]
    reconcile_existing()
    reconcile_existing()
    assert db.get(old) is None and db.get(saved)["files"] == before
    assert len(db.get(saved)["options"]["browser_replaced_records"]) == 1
    assert db.get(saved)["options"]["source"] == "instagram_saved"
