import pytest
from app import extractor, db, tasks
from app.social_media import (
    parse_facebook,
    parse_threads,
    TikTokMediaIE,
    TwitterMediaIE,
    PublicJSON,
)
from app.urls import normalize


def test_social_image_url_shapes():
    for url, platform in [
        ("https://www.facebook.com/share/p/SampleShare/", "facebook"),
        (
            "https://www.facebook.com/groups/example.group/permalink/1234567890123456/",
            "facebook",
        ),
        ("https://www.facebook.com/photo.php?fbid=123456789", "facebook"),
        ("https://www.tiktok.com/@test/photo/123456789", "tiktok"),
        ("https://x.com/test/status/123456789/photo/1", "x"),
    ]:
        assert normalize(url)[1] == platform


def test_facebook_original_attachments_only():
    image = lambda identifier: {
        "__typename": "Photo",
        "id": identifier,
        "image": {
            "uri": f"https://example.com/{identifier}.jpg",
            "width": 1600,
            "height": 1200,
        },
    }
    data = {
        "__typename": "Story",
        "post_id": "1234567890123456",
        "attachments": [
            {"media": image("one")},
            {"media": image("two")},
            {
                "media": {
                    "__typename": "Video",
                    "id": "three",
                    "browser_native_hd_url": "https://example.com/three.mp4",
                }
            },
        ],
    }
    result = parse_facebook(
        [{"unrelated": image("ignored")}, data],
        "https://www.facebook.com/groups/example.group/posts/1234567890123456/",
    )
    assert [item["id"] for item in result["entries"]] == ["one", "two", "three"]
    parser = PublicJSON()
    parser.feed('<meta property="og:image" content="https://example.com/preview.jpg">')
    with pytest.raises(ValueError, match="MEDIA_DATA_UNAVAILABLE"):
        parse_facebook(
            parser.documents,
            "https://www.facebook.com/groups/example.group/posts/1234567890123456/",
        )


def test_threads_matches_exact_post_not_recommendations():
    with extractor.SafeDL({"quiet": True}) as ydl:

        def post(code):
            return {
                "pk": "123",
                "code": code,
                "media_type": 1,
                "image_versions2": {
                    "candidates": [
                        {
                            "url": "https://example.com/" + code + ".jpg",
                            "width": 1000,
                            "height": 900,
                        }
                    ]
                },
            }

        result = parse_threads(
            [post("wrong"), post("correct")],
            "https://www.threads.com/@user/post/correct",
            ydl,
        )
        assert result["media_type"] == "image" and result["image_url"].endswith(
            "correct.jpg"
        )


def test_tiktok_slideshow_preserves_images_and_sound():
    with extractor.SafeDL({"quiet": True}) as ydl:
        ie = TikTokMediaIE(ydl)
        result = ie._parse_aweme_video_web(
            {
                "id": "123",
                "desc": "slide",
                "imagePost": {
                    "images": [
                        {"imageURL": {"urlList": ["https://example.com/1.jpg"]}},
                        {"imageURL": {"urlList": ["https://example.com/2.jpg"]}},
                    ]
                },
                "music": {"playUrl": "https://example.com/sound.m4a"},
            },
            "https://www.tiktok.com/@user/photo/123",
            "123",
        )
        assert [item["media_type"] for item in result["entries"]] == [
            "image",
            "image",
            "audio",
        ]


def test_x_photo_mixed_with_video(monkeypatch):
    with extractor.SafeDL({"quiet": True}) as ydl:
        ie = TwitterMediaIE(ydl)
        monkeypatch.setattr(
            ie,
            "_extract_status",
            lambda _: {
                "user": {"name": "test"},
                "extended_entities": {
                    "media": [
                        {
                            "id_str": "photo",
                            "type": "photo",
                            "media_url_https": "https://pbs.twimg.com/media/test.jpg",
                            "original_info": {"width": 2000, "height": 1000},
                        },
                        {
                            "id_str": "video",
                            "type": "video",
                            "video_info": {"variants": [{}]},
                        },
                    ]
                },
            },
        )
        monkeypatch.setattr(
            ie,
            "_extract_variant_formats",
            lambda *args: (
                [{"url": "https://example.com/video.mp4", "protocol": "https"}],
                {},
            ),
        )
        result = ie._real_extract("https://x.com/test/status/123456789")
        assert [item["media_type"] for item in result["entries"]] == ["image", "video"]
        assert "name=orig" in result["entries"][0]["image_url"]


def test_bulk_delete_preserves_active_and_clear_draft_is_separate(client):
    ids = client.post(
        "/api/jobs",
        json={
            "urls": [
                "https://www.instagram.com/p/delete1/",
                "https://www.instagram.com/p/delete2/",
            ]
        },
    ).json()["added"]
    db.update(ids[1], status="extracting")
    result = client.post("/api/jobs/delete", json={"ids": ids}).json()
    assert result == {"deleted": [ids[0]], "skipped": [ids[1]]}
    tasks.run(ids[0], "metadata", 0)  # stale queued work safely ignores deleted jobs
    assert db.get(ids[0]) is None and db.get(ids[1]) is not None
    assert client.delete("/api/imports/instagram-saved/draft").status_code == 200
    assert db.get(ids[1]) is not None
