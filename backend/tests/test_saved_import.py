import io
import json
import zipfile
import pytest
from app import db, extractor, tasks, saved_import, main

IG = "https://www.instagram.com/p/SamplePost01/"
REEL = "https://www.instagram.com/reel/SampleReel02/"
META = {
    "id": "abc",
    "title": "test",
    "formats": [
        {
            "url": "https://example.com/video.mp4",
            "protocol": "https",
            "vcodec": "h264",
            "acodec": "aac",
            "height": 1080,
        }
    ],
}


def export_fixture():
    return json.dumps(
        {
            "saved_saved_media": [
                {
                    "title": "artist",
                    "string_map_data": {"Saved on": {"href": IG, "timestamp": 1234}},
                },
                {
                    "string_list_data": [
                        {"href": IG.replace("/p/", "/reel/") + "?tracking=1"}
                    ]
                },
                {"string_map_data": {"Saved on": {"href": REEL}}},
                {"string_list_data": [{"href": "https://www.instagram.com/artist/"}]},
                {
                    "string_list_data": [
                        {"href": "https://instagram.com.evil.example/p/a/"}
                    ]
                },
            ]
        }
    ).encode()


def test_official_shapes_and_canonical_links():
    result = saved_import.parse_export(export_fixture(), "saved_posts.json")
    assert result["urls"] == [IG, REEL.replace("/reel/", "/p/")]
    assert result["duplicates"] == 1 and result["ignored"] == 2
    result = saved_import.parse_export(
        json.dumps(
            {
                "saved": [
                    {"href": "https://www.instagram.com/artist.name/p/SamplePost01/"}
                ]
            }
        ).encode(),
        "saved_posts_1.json",
    )
    assert result["urls"] == [IG]


def test_zip_only_reads_saved_and_html_never_executes(tmp_path):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("your_instagram_activity/saved/saved_posts.json", export_fixture())
        z.writestr(
            "../../saved_collections.html",
            f'<script>throw 1</script><a href="{REEL}?a=1&amp;b=2">saved</a>',
        )
        z.writestr(
            "messages/inbox/messages.json",
            json.dumps({"href": "https://www.instagram.com/p/PrivateMessage/"}),
        )
        z.writestr("run.py", "raise RuntimeError()")
    result = saved_import.parse_export(out.getvalue(), "instagram.zip")
    assert (
        len(result["urls"]) == 2
        and result["duplicates"] == 2
        and len(result["files"]) == 2
    )
    assert not (tmp_path / "saved_collections.html").exists()


@pytest.mark.parametrize(
    "name,data",
    [
        ("messages.json", b"{}"),
        ("saved_posts.json", b"{bad"),
        ("export.zip", b"bad"),
        ("saved_posts.json", b'{"saved": []}'),
    ],
)
def test_invalid_exports(name, data):
    with pytest.raises(ValueError):
        saved_import.parse_export(data, name)


def test_compressed_limit(monkeypatch):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("saved_posts.json", b"x" * 1024)
    monkeypatch.setattr(saved_import, "TEXT_LIMIT", 100)
    with pytest.raises(ValueError, match="64MB"):
        saved_import.parse_export(out.getvalue(), "export.zip")


def test_preview_does_not_register_and_repeated_import_dedups(client, monkeypatch):
    r = client.post(
        "/api/imports/instagram-saved?filename=saved_posts.json",
        content=export_fixture(),
    )
    assert r.status_code == 200
    assert len(r.json()["urls"]) == 2 and r.json()["available_slots"] == main.MAX_JOBS
    assert client.get("/api/jobs").json()["jobs"] == []
    reg = client.post(
        "/api/jobs",
        json={
            "urls": r.json()["urls"],
            "auto_download": True,
            "source": "instagram_saved",
        },
    ).json()
    jid = reg["added"][0]
    monkeypatch.setattr(extractor, "extract", lambda j: dict(META))
    tasks.run(jid, "metadata", 0)
    job = db.get(jid)
    assert (job["status"], job["phase"], job["attempt"]) == (
        "queued_download",
        "download",
        1,
    )
    second = client.post(
        "/api/jobs",
        json={
            "urls": r.json()["urls"],
            "auto_download": True,
            "source": "instagram_saved",
        },
    ).json()
    assert second["added"] == [] and len(second["duplicates"]) == 2
    assert db.get(jid)["attempt"] == 1
    assert db.get(jid)["options"]["source"] == "instagram_saved"
    assert (
        client.post(
            "/api/imports/instagram-saved?filename=saved_posts.json",
            content=export_fixture(),
        ).json()["already_registered"]
        == 2
    )


def test_saved_duplicate_ready_and_carousel_children(client, monkeypatch):
    jid = client.post("/api/jobs", json={"urls": [IG]}).json()["added"][0]
    monkeypatch.setattr(
        extractor,
        "extract",
        lambda j: {"_type": "playlist", "entries": [dict(META), dict(META, id="b")]},
    )
    tasks.run(jid, "metadata", 0)
    children = [
        j for j in client.get("/api/jobs").json()["jobs"] if j["parent_id"] == jid
    ]
    monkeypatch.setattr(extractor, "extract", lambda j: dict(META))
    for child in children:
        tasks.run(child["id"], "metadata", 0)
    client.post(
        "/api/jobs",
        json={"urls": [IG], "auto_download": True, "source": "instagram_saved"},
    )
    for child in children:
        job = db.get(child["id"])
        assert job["options"]["source"] == "instagram_saved"
        assert (job["status"], job["attempt"]) == ("queued_download", 1)


def test_auto_carousel_inherits_and_nonvideo_is_explicit(client, monkeypatch):
    jid = client.post(
        "/api/jobs",
        json={"urls": [IG], "auto_download": True, "source": "instagram_saved"},
    ).json()["added"][0]
    monkeypatch.setattr(
        extractor,
        "extract",
        lambda j: {"_type": "playlist", "entries": [dict(META), dict(META, id="b")]},
    )
    tasks.run(jid, "metadata", 0)
    children = [
        j for j in client.get("/api/jobs").json()["jobs"] if j["parent_id"] == jid
    ]
    assert all(
        j["options"]["auto_download"] and j["options"]["source"] == "instagram_saved"
        for j in children
    )
    monkeypatch.setattr(
        extractor,
        "extract",
        lambda j: {
            "formats": [
                {
                    "url": "https://example.com/a",
                    "protocol": "https",
                    "vcodec": "none",
                    "acodec": "aac",
                }
            ]
        },
    )
    tasks.run(children[0]["id"], "metadata", 0)
    assert db.get(children[0]["id"])["status"] == "queued_download"
    assert db.get(children[0]["id"])["metadata"]["media_type"] == "audio"


def test_capacity_rolls_back_without_dropping_links(client, monkeypatch):
    client.post("/api/jobs", json={"urls": [IG]})
    monkeypatch.setattr(main, "MAX_JOBS", 2)
    response = client.post(
        "/api/jobs", json={"urls": [IG, REEL, "https://www.instagram.com/p/third/"]}
    )
    assert response.status_code == 409
    assert len(client.get("/api/jobs").json()["jobs"]) == 1
    assert len(client.post("/api/jobs", json={"urls": [IG, REEL]}).json()["added"]) == 1
    assert (
        len(client.post("/api/jobs", json={"urls": [IG, REEL]}).json()["duplicates"])
        == 2
    )
