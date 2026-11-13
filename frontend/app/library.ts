import type { MediaJob } from "./media";

import { busyStates } from "./media.ts";
function stateOf(items: MediaJob[]) {
  if (items.every((j) => j.status === "completed")) return "completed";
  const running = items.find((j) => busyStates.has(j.status));
  if (running) return running.status;
  if (items.some((j) => j.status === "failed")) return "failed";
  if (items.some((j) => j.status === "ready")) return "ready";
  return items[0]?.status || "ready";
}
export function sourceKey(job: MediaJob) {
  return job.url ? `${job.platform}:${job.url}` : job.id;
}
export function buildLibrary(jobs: MediaJob[]): MediaJob[] {
  const roots = new Map<string, MediaJob>();
  const albums = new Map<string, MediaJob[]>();
  const videos: MediaJob[] = [];
  for (const j of jobs) {
    if (!j.parent_id) {
      const key = sourceKey(j),
        old = roots.get(key);
      if (!old || j.created_at < old.created_at) roots.set(key, j);
    }
  }
  for (const job of jobs) {
    if (job.status === "expanded" || job.metadata.media_type === "collection")
      continue;
    const pendingAttachment =
      Boolean(job.parent_id) &&
      !job.metadata.media_type &&
      job.platform !== "recording";
    if (job.metadata.media_type === "image" || pendingAttachment) {
      const key = sourceKey(job);
      const group = albums.get(key) || [];
      group.push(job);
      albums.set(key, group);
    } else videos.push(job);
  }
  const counts = new Map<string, MediaJob[]>();
  for (const job of videos) {
    if (job.metadata.media_type === "video") {
      const key = sourceKey(job),
        group = counts.get(key) || [];
      group.push(job);
      counts.set(key, group);
    }
  }
  const labels = new Map<string, string>();
  for (const members of counts.values()) {
    if (members.length < 2) continue;
    members.sort((a, b) => (a.entry_index ?? 0) - (b.entry_index ?? 0));
    members.forEach((j, i) =>
      labels.set(j.id, `영상 ${i + 1} / ${members.length}`),
    );
  }
  const result = videos.map((j) => ({
    ...j,
    created_at: roots.get(sourceKey(j))?.created_at || j.created_at,
    job_ids: [j.id],
    display_caption: labels.get(j.id),
  }));
  for (const [key, items] of albums) {
    items.sort(
      (a, b) =>
        (a.entry_index ?? -1) - (b.entry_index ?? -1) ||
        a.created_at - b.created_at,
    );
    const root = roots.get(key) || items[0];
    const images = items.filter((j) => j.metadata.media_type === "image");
    const cover =
      images.find((j) => j.status === "completed") || images[0] || root;
    const complete = items.filter((j) => j.status === "completed").length;
    const unknown = items.length - images.length;
    result.push({
      ...root,
      id: "album:" + key,
      job_ids: items.map((j) => j.id),
      members: items,
      image_count: images.length,
      pending_count: unknown,
      completed_count: complete,
      status: stateOf(items),
      progress: (100 * complete) / items.length,
      files: items.flatMap((j) => j.files),
      retryable: Number(items.some((j) => j.retryable)),
      metadata: {
        ...cover.metadata,
        media_type: "image_group",
        title: `${cover.metadata.uploader || root.metadata.uploader || "게시물"} · ${images.length ? "사진 묶음" : "미디어 확인 중"}`,
      },
      display_caption: [
        images.length ? `사진 ${images.length}장` : "",
        unknown ? `미확인 ${unknown}개` : "",
      ]
        .filter(Boolean)
        .join(" · "),
    });
  }
  return result.sort(
    (a, b) =>
      b.created_at - a.created_at ||
      (a.entry_index ?? -1) - (b.entry_index ?? -1),
  );
}
export function expandSelection(
  items: MediaJob[],
  ids: Iterable<string>,
): string[] {
  const selected = new Set(ids);
  return [
    ...new Set(
      items
        .filter((j) => selected.has(j.id))
        .flatMap((j) => j.job_ids || [j.id]),
    ),
  ];
}
