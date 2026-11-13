import test from "node:test";
import assert from "node:assert/strict";
import { buildLibrary, expandSelection } from "../app/library.ts";
const url = "https://www.instagram.com/p/post1/";
function job(id, type, status = "completed", index = 0) {
  return {
    id,
    url,
    platform: "instagram",
    status,
    mode: "video",
    progress: 100,
    created_at: 10 + index,
    parent_id: id === "parent" ? undefined : "parent",
    entry_index: id === "parent" ? null : index,
    metadata: {
      title: "Video by author",
      uploader: "author",
      media_type: type,
    },
    options: { source: "instagram_saved" },
    files:
      status === "completed"
        ? [{ id: "f" + id, name: id + ".jpg", size: 100 }]
        : [],
    retryable: 0,
  };
}
test("one link with ten pictures becomes one album without copying or dropping files", () => {
  const raw = [
    job("parent", "collection", "expanded"),
    ...Array.from({ length: 10 }, (_, i) =>
      job("p" + i, "image", "completed", i),
    ),
  ];
  const before = JSON.stringify(raw),
    items = buildLibrary(raw);
  assert.equal(items.length, 1);
  assert.equal(items[0].image_count, 10);
  assert.equal(items[0].files.length, 10);
  assert.equal(items[0].members.length, 10);
  assert.equal(items[0].status, "completed");
  assert.equal(JSON.stringify(raw), before);
  assert.deepEqual(
    expandSelection(items, [items[0].id]),
    Array.from({ length: 10 }, (_, i) => "p" + i),
  );
});
test("mixed posts group only photos and keep each video separate", () => {
  const raw = [
    job("parent", "collection", "expanded"),
    job("p1", "image"),
    job("v1", "video", "completed", 1),
    job("v2", "video", "completed", 2),
    job("p2", "image", "completed", 3),
  ];
  const items = buildLibrary(raw);
  assert.equal(items.length, 3);
  assert.equal(items.filter((j) => j.members).length, 1);
  assert.equal(items.find((j) => j.members).members.length, 2);
  assert.equal(items.find((j) => j.id === "v1").display_caption, "영상 1 / 2");
  assert.equal(items.find((j) => j.id === "v2").display_caption, "영상 2 / 2");
  assert.deepEqual(expandSelection(items, ["v1"]), ["v1"]);
});
test("unknown attachments stay grouped until confirmed and do not pretend to be images", () => {
  const pending = job("u", undefined, "queued_metadata", 2),
    photo = job("p", "image");
  const raw = [job("parent", "collection", "expanded"), photo, pending];
  let items = buildLibrary(raw);
  assert.equal(items.length, 1);
  assert.equal(items[0].image_count, 1);
  assert.equal(items[0].pending_count, 1);
  assert.equal(items[0].status, "queued_metadata");
  const key = items[0].id;
  items = buildLibrary([
    raw[0],
    photo,
    { ...pending, metadata: { media_type: "video" }, status: "completed" },
  ]);
  assert.equal(items.length, 2);
  assert.equal(items.find((j) => j.members).id, key);
  assert.equal(items.find((j) => j.members).pending_count, 0);
});
test("same author and title on different links remain different albums", () => {
  const a = job("a", "image"),
    b = { ...job("b", "image"), url: "https://www.instagram.com/p/post2/" };
  assert.equal(buildLibrary([a, b]).length, 2);
});
test("repeated import/manual photo records of same URL share one album, all originals retained", () => {
  const a = { ...job("a", "image"), parent_id: undefined },
    b = { ...job("b", "image"), parent_id: undefined };
  const items = buildLibrary([a, b]);
  assert.equal(items.length, 1);
  assert.deepEqual(expandSelection(items, [items[0].id]), ["a", "b"]);
});
test("failed photo is accessible and all children remain represented", () => {
  const items = buildLibrary([
    job("parent", "collection", "expanded"),
    job("ok", "image"),
    { ...job("bad", "image", "failed", 1), retryable: 1 },
  ]);
  assert.equal(items[0].status, "failed");
  assert.equal(items[0].completed_count, 1);
  assert.equal(items[0].retryable, 1);
});
