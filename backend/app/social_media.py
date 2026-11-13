"""Public structured media only. Never use link previews as post originals."""

import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from yt_dlp.extractor.tiktok import TikTokIE
from yt_dlp.extractor.twitter import TwitterIE

from .instagram_media import InstagramMediaIE


def photo(identifier, url, title="", width=None, height=None, uploader=""):
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("No media: invalid photo URL")
    return {
        "id": str(identifier),
        "title": title or "Image",
        "media_type": "image",
        "image_url": url,
        "thumbnail": url,
        "width": width,
        "height": height,
        "uploader": uploader,
        "formats": [
            {
                "url": url,
                "protocol": "https",
                "vcodec": "none",
                "acodec": "none",
                "width": width,
                "height": height,
            }
        ],
    }


def collection(identifier, title, items):
    if not items:
        raise ValueError("No media: no original attachments")
    return (
        items[0]
        if len(items) == 1
        else {
            "_type": "playlist",
            "id": str(identifier),
            "title": title or "Media post",
            "entries": items,
        }
    )


class TwitterMediaIE(TwitterIE):
    def _real_extract(self, url):
        post_id = self._match_id(url)
        status = self._extract_status(post_id)
        media = (status.get("extended_entities") or {}).get("media") or []
        if not any(m.get("type") == "photo" for m in media):
            # Reuse the same normal API response; no second request or quoted-photo scraping.
            self._extract_status = lambda _: status
            return super()._real_extract(url)
        user = status.get("user") or {}
        title = status.get("full_text") or status.get("text") or "X media"
        items = []
        for index, item in enumerate(media):
            identifier = (
                item.get("id_str") or item.get("id") or f"{post_id}-{index + 1}"
            )
            if item.get("type") == "photo":
                raw = item.get("media_url_https") or item.get("media_url")
                parts = urlsplit(raw or "")
                query = parse_qs(parts.query)
                query["name"] = ["orig"]
                original = urlunsplit(
                    (
                        parts.scheme,
                        parts.netloc,
                        parts.path,
                        urlencode(query, doseq=True),
                        "",
                    )
                )
                size = item.get("original_info") or {}
                items.append(
                    photo(
                        identifier,
                        original,
                        title,
                        size.get("width"),
                        size.get("height"),
                        user.get("name", ""),
                    )
                )
            elif item.get("type") in ("video", "animated_gif"):
                formats = []
                for variant in (item.get("video_info") or {}).get("variants", []):
                    extracted, _ = self._extract_variant_formats(variant, post_id)
                    formats.extend(extracted)
                items.append(
                    {
                        "id": str(identifier),
                        "title": title,
                        "media_type": "video",
                        "formats": formats,
                        "uploader": user.get("name", ""),
                        "thumbnail": item.get("media_url_https"),
                    }
                )
        return collection(post_id, title, items)


class TikTokMediaIE(TikTokIE):
    _VALID_URL = r"https?://(?:www\.)?tiktok\.com/@(?P<user_id>[^/]+)/(?:video|photo)/(?P<id>\d+)"

    def _real_extract(self, url):
        if "/photo/" not in url:
            return super()._real_extract(url)
        identifier = self._match_id(url)
        data, status = self._extract_web_data_and_status(url, identifier)
        if status in (10216, 10222):
            self.raise_login_required("This post requires account access")
        if status == 10204:
            raise ValueError("Access denied by TikTok")
        if not data or status != 0:
            raise ValueError(f"Media not available, status {status}")
        return self._parse_aweme_video_web(data, url, identifier)

    def _parse_aweme_video_web(self, data, url, identifier, extract_flat=False):
        images = (
            (data.get("imagePost") or {}).get("images")
            or (data.get("image_post_info") or {}).get("images")
            or []
        )
        if not images:
            return super()._parse_aweme_video_web(data, url, identifier, extract_flat)
        title = data.get("desc") or "TikTok images"
        items = []
        for index, item in enumerate(images):
            source = (
                item.get("imageURL")
                or item.get("image_url")
                or item.get("displayImage")
                or {}
            )
            urls = source.get("urlList") or source.get("url_list") or []
            original = next(
                (u for u in urls if isinstance(u, str) and u.startswith("https://")),
                None,
            )
            if not original:
                raise ValueError("MEDIA_DATA_UNAVAILABLE: image item missing")
            items.append(
                photo(
                    f"{identifier}-image-{index + 1}",
                    original,
                    title,
                    source.get("width"),
                    source.get("height"),
                )
            )
        music = data.get("music") or {}
        audio = music.get("playUrl")
        if not audio:
            audio = next(
                iter((music.get("play_url") or {}).get("url_list") or []), None
            )
        if audio and audio.startswith("https://"):
            items.append(
                {
                    "id": f"{identifier}-audio",
                    "title": music.get("title") or title,
                    "media_type": "audio",
                    "formats": [
                        {
                            "url": audio,
                            "protocol": "https",
                            "vcodec": "none",
                            "acodec": "unknown",
                            "ext": "m4a",
                        }
                    ],
                }
            )
        return collection(identifier, title, items)


class PublicJSON(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.parts = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script":
            self.capture = (
                a.get("type") in ("application/json", "application/ld+json")
                or "data-sjs" in a
            )
            self.parts = []

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.capture:
            try:
                self.documents.append(json.loads("".join(self.parts)))
            except (ValueError, RecursionError):
                pass
            self.capture = False
            self.parts = []


def walk(value):
    stack = [value]
    count = 0
    while stack:
        node = stack.pop()
        count += 1
        if count > 300000:
            raise ValueError("MEDIA_DATA_UNAVAILABLE: page data too complex")
        if isinstance(node, dict):
            yield node
            stack.extend(reversed(list(node.values())))
        elif isinstance(node, list):
            stack.extend(reversed(node))


def parse_threads(documents, url, ydl):
    code = urlsplit(url).path.rstrip("/").split("/")[-1]
    for node in walk(documents):
        if node.get("code") == code and (
            node.get("media_type") in (1, 2, 8) or node.get("carousel_media")
        ):
            return InstagramMediaIE(ydl)._extract_product(
                node, video_id=code, get_comments=False
            )
    raise ValueError(
        "MEDIA_DATA_UNAVAILABLE: original Threads post is absent from public page"
    )


def parse_facebook(documents, url):
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    ids = set(
        re.findall(r"\d{6,}", parts.path)
        + query.get("fbid", [])
        + query.get("story_fbid", [])
    )
    target = None
    for node in walk(documents):
        if (
            node.get("__typename") in ("Story", "Photo")
            and str(node.get("post_id") or node.get("story_fbid") or node.get("id"))
            in ids
        ):
            target = node
            break
    if not target:
        raise ValueError(
            "MEDIA_DATA_UNAVAILABLE: original Facebook attachments are absent from public page"
        )
    scope = (
        target
        if target.get("__typename") == "Photo"
        else target.get("attachments")
        or target.get("comet_sections", {}).get("content", {})
    )
    items = []
    seen = set()
    for node in walk(scope):
        kind = node.get("__typename")
        identifier = str(node.get("id", ""))
        if not identifier or identifier in seen or kind not in ("Photo", "Video"):
            continue
        title = (
            target.get("message", {}).get("text", "")
            if isinstance(target.get("message"), dict)
            else "Facebook media"
        )
        if kind == "Photo":
            candidates = [
                node.get(k)
                for k in ("photo_image", "image", "large_share_image", "viewer_image")
            ]
            candidates = [
                c
                for c in candidates
                if isinstance(c, dict) and str(c.get("uri", "")).startswith("https://")
            ]
            if not candidates:
                raise ValueError("MEDIA_DATA_UNAVAILABLE: photo missing")
            largest = max(
                candidates, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0)
            )
            items.append(
                photo(
                    identifier,
                    largest["uri"],
                    title,
                    largest.get("width"),
                    largest.get("height"),
                )
            )
        else:
            formats = [
                {
                    "url": node[k],
                    "protocol": "https",
                    "format_id": k,
                    "vcodec": "unknown",
                    "acodec": "unknown",
                }
                for k in ("browser_native_hd_url", "browser_native_sd_url")
                if str(node.get(k, "")).startswith("https://")
            ]
            if not formats:
                raise ValueError("MEDIA_DATA_UNAVAILABLE: mixed-post video missing")
            items.append(
                {
                    "id": identifier,
                    "title": title,
                    "media_type": "video",
                    "formats": formats,
                }
            )
        seen.add(identifier)
    return collection(next(iter(ids), "facebook"), "Facebook media", items)


def extract_public_page(ydl, url, platform):
    with ydl.urlopen(url) as response:
        body = response.read(12 * 1024**2 + 1)
        final_url = response.url
    if len(body) > 12 * 1024**2:
        raise ValueError("MEDIA_DATA_UNAVAILABLE: page too large")
    if "/login" in urlsplit(final_url).path or "/accounts/" in urlsplit(final_url).path:
        raise ValueError("Login required")
    parser = PublicJSON()
    parser.feed(body.decode("utf-8", "replace"))
    return (
        parse_threads(parser.documents, final_url, ydl)
        if platform == "threads"
        else parse_facebook(parser.documents, final_url)
    )
