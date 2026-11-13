"use strict";
const { URL } = require("node:url");
function postURL(raw) {
  const u = new URL(raw);
  const match = u.pathname.match(
    /^\/(?:[A-Za-z0-9_.]+\/)?(?:p|reel|reels)\/([\w-]+)\/?$/,
  );
  if (
    u.protocol !== "https:" ||
    u.username ||
    u.password ||
    u.port ||
    !["instagram.com", "www.instagram.com"].includes(u.hostname) ||
    !match
  )
    throw Error("Instagram 게시물 또는 릴스 링크를 입력하세요.");
  return "https://www.instagram.com/p/" + match[1] + "/";
}
function siteURL(raw) {
  try {
    const u = new URL(raw);
    return (
      u.protocol === "https:" &&
      !u.username &&
      !u.password &&
      !u.port &&
      (u.hostname === "instagram.com" ||
        u.hostname.endsWith(".instagram.com") ||
        u.hostname === "facebook.com" ||
        u.hostname.endsWith(".facebook.com"))
    );
  } catch {
    return false;
  }
}
function mediaURL(raw) {
  const u = new URL(raw);
  const h = u.hostname;
  if (
    u.protocol !== "https:" ||
    u.username ||
    u.password ||
    u.port ||
    !["cdninstagram.com", "fbcdn.net"].some((d) => h.endsWith("." + d))
  )
    throw Error("지원하지 않는 미디어 주소입니다.");
  // These are transport byte ranges, not authentication parameters. Keep every signature.
  u.searchParams.delete("bytestart");
  u.searchParams.delete("byteend");
  return u.href;
}
function describeStream(raw) {
  try {
    const url = mediaURL(raw),
      u = new URL(url),
      encoded = u.searchParams.get("efg");
    if (!encoded || encoded.length > 4096) return null;
    // Instagram IDs can exceed JavaScript's safe integer range. Preserve their
    // original decimal digits before parsing instead of rounding or rejecting them.
    const text = Buffer.from(encoded, "base64url")
      .toString("utf8")
      .replace(
        /("(?:xpv_asset_id|video_id)"\s*:\s*)(\d+)(?=\s*[,}])/g,
        '$1"$2"',
      );
    const e = JSON.parse(text);
    const id = String(e.xpv_asset_id || e.video_id || "");
    const duration = Number(e.duration_s),
      bitrate = Number(e.bitrate) || 0;
    if (!/^\d+$/.test(id) || !Number.isFinite(duration) || duration <= 0)
      return null;
    return {
      id,
      duration,
      bitrate,
      audio: /audio/i.test(String(e.vencode_tag)),
      url,
    };
  } catch {
    return null;
  }
}
function choices(visible, observed) {
  const result = [];
  for (const m of visible) {
    if (m.encrypted) continue;
    if (m.kind === "image") {
      try {
        const url = mediaURL(m.url);
        if (!result.some((x) => x.image === url))
          result.push({
            kind: "image",
            image: url,
            width: m.width,
            height: m.height,
            label: `이미지 · ${m.width} × ${m.height}`,
            preview: url,
          });
      } catch {}
    } else if (
      m.kind === "video" &&
      visible.filter((v) => v.kind === "video").length === 1 &&
      Number.isFinite(m.duration) &&
      m.duration > 0
    ) {
      if (m.url?.startsWith("https:")) {
        try {
          result.push({
            kind: "video",
            video: mediaURL(m.url),
            label: `영상 · ${Math.round(m.duration)}초`,
            duration: m.duration,
            preview: m.poster || "",
          });
        } catch {}
      } else if (m.url?.startsWith("blob:")) {
        const groups = new Map();
        for (const raw of observed) {
          const s = describeStream(raw);
          if (!s || Math.abs(s.duration - m.duration) > 1.1) continue;
          const g = groups.get(s.id) || {};
          const key = s.audio ? "audio" : "video";
          if (!g[key] || s.bitrate > g[key].bitrate) g[key] = s;
          groups.set(s.id, g);
        }
        const withVideo = [...groups].filter(([, g]) => g.video);
        if (withVideo.length !== 1) continue;
        for (const [id, g] of withVideo) {
          result.push({
            kind: "video",
            video: g.video.url,
            audio: g.audio?.url,
            muted: !g.audio,
            duration: m.duration,
            asset: id,
            label: `영상 · ${Math.round(m.duration)}초${g.audio ? " · 오디오 포함" : " · 오디오 미확인 (무음 저장)"}${groups.size > 1 ? " · 후보 " + id.slice(-6) : ""}`,
            preview: m.poster || "",
          });
        }
      }
    }
  }
  return result.slice(0, 12);
}
module.exports = { postURL, siteURL, mediaURL, describeStream, choices };
