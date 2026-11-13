import json
from app import db, main


def test_5000_import_resume_failed_dedup_and_export(client):
    urls = [f"https://www.instagram.com/p/fixture{i}/" for i in range(5000)]
    raw = json.dumps({"saved": [{"href": u} for u in urls]}).encode()
    preview = client.post(
        "/api/imports/instagram-saved?filename=saved_posts.json", content=raw
    ).json()
    assert len(preview["urls"]) == 5000 and preview["available_slots"] >= 5000
    ids = []
    for n in range(0, 5000, 100):
        response = client.post(
            "/api/jobs",
            json={
                "urls": urls[n : n + 100],
                "source": "instagram_saved",
                "auto_download": True,
            },
        )
        assert response.status_code == 200, response.text
        ids.extend(response.json()["added"])
    assert len(ids) == 5000
    db.fail(ids[0], "AUTH_REQUIRED", "test", False)
    repeated = client.post(
        "/api/jobs",
        json={"urls": urls[:100], "source": "instagram_saved", "auto_download": True},
    ).json()
    assert repeated["added"] == [] and len(repeated["duplicates"]) == 100
    progress = {
        "draft_id": preview["draft_id"],
        "cursor": 2000,
        "added": 2000,
        "duplicates": 0,
        "auto": True,
    }
    assert (
        client.put("/api/imports/instagram-saved/draft", json=progress).status_code
        == 200
    )
    db.init()  # repeated initialization / app restart retains draft
    draft = client.get("/api/imports/instagram-saved/draft").json()["draft"]
    assert draft["cursor"] == 2000 and draft["preview"]["urls"][2000:] == urls[2000:]
    assert draft["preview"]["available_slots"] == main.MAX_JOBS - 5000
    initial = client.get("/api/jobs").json()
    assert len(initial["jobs"]) == 5000
    selection = client.post("/api/exports", json={"ids": ids}).json()["selection"]
    exported = client.get("/api/manifest.csv", params={"selection": selection})
    assert exported.status_code == 200 and len(exported.text.splitlines()) == 5001
    db.update(ids[1], progress=42)
    delta = client.get("/api/jobs", params={"since": initial["server_time"]}).json()
    assert [j["id"] for j in delta["jobs"]] == [ids[1]] and len(
        delta["all_ids"]
    ) == 5000
    assert client.delete("/api/jobs/" + ids[0]).status_code == 200
    delta2 = client.get("/api/jobs", params={"since": delta["server_time"]}).json()
    assert ids[0] not in delta2["all_ids"]


def test_desktop_queue_launches_three_without_duplicate_children(client, monkeypatch):
    from app import desktop_queue

    calls = []

    class Process:
        def __init__(self, args, **kwargs):
            calls.append(args)
            self.pid = 999

        def poll(self):
            return None

    monkeypatch.setattr(desktop_queue, "WORKERS", 3)
    monkeypatch.setattr(desktop_queue.subprocess, "Popen", Process)
    client.post(
        "/api/jobs",
        json={"urls": [f"https://www.instagram.com/p/parallel{i}/" for i in range(5)]},
    )
    runner = desktop_queue.LocalQueue()
    runner.tick()
    runner.tick()
    assert len(calls) == 3 and len({call[3] for call in calls}) == 3


def test_manual_registration_merges_existing_failed_id_instead_of_duplicating(client):
    url = "https://www.instagram.com/reel/sameid/?tracking=1"
    first = client.post("/api/jobs", json={"urls": [url]}).json()["added"][0]
    db.fail(first, "AUTH_REQUIRED", "test")
    repeat = client.post(
        "/api/jobs", json={"urls": ["https://www.instagram.com/p/sameid/"]}
    ).json()
    assert repeat["added"] == [] and repeat["duplicates"][0]["id"] == first
    assert len(client.get("/api/jobs").json()["jobs"]) == 1


def test_carousel_repeated_media_id_registers_only_once_and_keeps_entry_index(
    client, monkeypatch
):
    from app import extractor, tasks

    jid = client.post(
        "/api/jobs", json={"urls": ["https://www.instagram.com/p/carousel/"]}
    ).json()["added"][0]
    image = {
        "id": "photo1",
        "title": "picture",
        "media_type": "image",
        "image_url": "https://cdn.example/photo.jpg",
    }
    video = {
        "id": "video2",
        "title": "video",
        "media_type": "video",
        "formats": [{"protocol": "https", "vcodec": "h264", "acodec": "aac"}],
    }
    monkeypatch.setattr(
        extractor,
        "extract",
        lambda _: {"_type": "playlist", "entries": [image, image, video]},
    )
    tasks.run(jid, "metadata", 0)
    with db.connect() as c:
        children = [
            db.decode(r)
            for r in c.execute(
                "SELECT * FROM jobs WHERE parent_id=? ORDER BY entry_index", (jid,)
            )
        ]
    assert len(children) == 2 and [j["entry_index"] for j in children] == [0, 2]
    assert [j["metadata"]["media_type"] for j in children] == ["image", "video"]
