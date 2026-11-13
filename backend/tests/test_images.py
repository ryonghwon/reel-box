import io
import subprocess
import pytest
from app import extractor, tasks, db
from app.instagram_media import InstagramMediaIE


def test_instagram_photo_and_mixed_carousel_preserve_types():
    with extractor.SafeDL({"quiet": True}) as ydl:
        ie = InstagramMediaIE(ydl)
        photo = {
            "pk": "1",
            "media_type": 1,
            "image_versions2": {
                "candidates": [
                    {
                        "url": "https://example.com/small.jpg",
                        "width": 320,
                        "height": 240,
                    },
                    {
                        "url": "https://example.com/large.jpg",
                        "width": 1600,
                        "height": 1200,
                    },
                ]
            },
        }
        video = {
            "pk": "2",
            "media_type": 2,
            "video_versions": [
                {"url": "https://example.com/video.mp4", "width": 1920, "height": 1080}
            ],
            "image_versions2": {
                "candidates": [
                    {
                        "url": "https://example.com/thumb.jpg",
                        "width": 320,
                        "height": 240,
                    }
                ]
            },
        }
        result = ie._extract_product(
            {"pk": "9", "carousel_media": [photo, video]}, get_comments=False
        )
        assert [item["media_type"] for item in result["entries"]] == ["image", "video"]
        assert result["entries"][0]["image_url"].endswith("/large.jpg")
        assert "image_url" not in result["entries"][1]
        with pytest.raises(ValueError, match="audio"):
            extractor.verify_media(result["entries"][0], "audio")
        # A broken video must not be silently replaced by its thumbnail.
        broken = ie._extract_product_media({**video, "video_versions": []})
        assert broken["media_type"] == "video" and "image_url" not in broken


def test_image_download_preserves_original_bytes(client, tmp_path, monkeypatch):
    original = tmp_path / "source.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:size=640x480",
            "-frames:v",
            "1",
            "-update",
            "1",
            str(original),
        ],
        check=True,
    )
    content = original.read_bytes()
    monkeypatch.setattr(
        extractor.SafeDL, "urlopen", lambda self, request: io.BytesIO(content)
    )
    info = {
        "id": "photo",
        "title": "Photo",
        "media_type": "image",
        "image_url": "https://example.com/original.jpg",
        "width": 640,
        "height": 480,
    }
    monkeypatch.setattr(extractor, "extract", lambda job, *args: info)
    jid = client.post(
        "/api/jobs",
        json={
            "urls": ["https://www.instagram.com/p/testPhoto/"],
            "auto_download": True,
        },
    ).json()["added"][0]
    tasks.run(jid, "metadata", 0)
    tasks.run(jid, "download", 1)
    job = db.get(jid)
    assert job["status"] == "completed" and job["metadata"]["media_type"] == "image"
    assert client.get("/api/files/" + job["files"][0]["id"]).content == content
    assert job["files"][0]["name"].endswith(".jpg")
    assert client.post("/api/jobs/" + jid + "/compatible").status_code == 409
