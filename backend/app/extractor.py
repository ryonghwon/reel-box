import os
import time
import json
import subprocess
from itertools import islice
from urllib.parse import urlsplit
import yt_dlp
from yt_dlp.extractor import gen_extractor_classes
from .config import MAX_BYTES
from .urls import assert_public_url


class QuietLogger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


class SafeDL(yt_dlp.YoutubeDL):
    def urlopen(self, req):
        url = req if isinstance(req, str) else req.url
        assert_public_url(url)
        return super().urlopen(req)


def options(job, downloading=False):
    # Fixed, server-owned options. No cookies, credentials, arbitrary flags or plugins.
    return {
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
        "socket_timeout": 20,
        "retries": 1,
        "fragment_retries": 1,
        "sleep_interval_requests": 1,
        "sleep_interval": 2,
        "max_sleep_interval": 3,
        "extractor_retries": 1,
        "skip_unavailable_fragments": False,
        "noplaylist": not job["options"].get("collections", False),
        "playlistend": job["options"].get("collection_limit", 25) + 1,
        "lazy_playlist": True,
        "cachedir": False,
        "geo_bypass": False,
        "proxy": os.getenv("EGRESS_PROXY", ""),
        "js_runtimes": {
            "node": {"path": os.environ["REELBOX_NODE"]}
            if os.getenv("REELBOX_NODE")
            else {}
        },
        "remote_components": [],
        "hls_prefer_native": True,
        "max_filesize": MAX_BYTES,
        "format": "bestaudio/best"
        if job["mode"] == "audio"
        else "bestvideo*+bestaudio/best",
        "format_sort": [
            "quality",
            "res",
            "fps",
            "hdr:12",
            "vcodec",
            "channels",
            "acodec",
            "size",
            "br",
            "asr",
            "proto",
            "ext",
            "hasaud",
            "source",
            "id",
        ],
        "merge_output_format": "mp4/mkv",
        "overwrites": True,
        "continuedl": False,
        "concurrent_fragment_downloads": 1,
        "extract_flat": "in_playlist"
        if job["platform"] == "youtube"
        and job["options"].get("collections")
        and job.get("entry_index") is None
        and not downloading
        else False,
    }


def is_collection(info):
    return info.get("_type") in ("playlist", "multi_video") or "entries" in info


def entries(info, limit):
    return list(islice((e for e in (info.get("entries") or []) if e), limit + 1))


def verify_media(info, mode):
    if info.get("media_type") == "image":
        if mode == "audio":
            raise ValueError("No formats: image has no audio")
        if not info.get("image_url"):
            raise ValueError("No media: image URL missing")
        return info
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
        raise ValueError("LIVE_UNSUPPORTED")
    formats = info.get("formats") or []
    if info.get("has_drm") or (formats and all(f.get("has_drm") for f in formats)):
        raise ValueError("DRM protected")
    # Only native HTTP downloaders; FFmpeg is used on local files for merging/extraction.
    usable = [
        f
        for f in formats
        if not f.get("has_drm")
        and f.get("protocol") in ("http", "https", "m3u8_native", "http_dash_segments")
    ]
    if formats and not usable:
        raise ValueError("No formats")
    if formats:
        info["formats"] = usable
    if mode == "video" and formats and all(f.get("vcodec") == "none" for f in usable):
        info["media_type"] = "audio"
    if mode == "audio" and formats and all(f.get("acodec") == "none" for f in usable):
        raise ValueError("No formats: audio missing")
    return info


def metadata(info):
    thumb = info.get("thumbnail")
    if not thumb and info.get("thumbnails"):
        thumb = info["thumbnails"][-1].get("url")
    if thumb and urlsplit(thumb).scheme != "https":
        thumb = None
    formats = [f for f in info.get("formats", []) if not f.get("has_drm")]
    return {
        "id": str(info.get("id", "")),
        "title": str(info.get("title") or info.get("description") or "제목 없음")[:300],
        "uploader": str(info.get("uploader") or info.get("channel") or "")[:150],
        "duration": info.get("duration"),
        "thumbnail": thumb,
        "width": info.get("width"),
        "height": info.get("height"),
        "max_height": max(
            (f.get("height") or 0 for f in formats), default=info.get("height") or 0
        ),
        "format_count": len(formats),
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "upload_date": info.get("upload_date"),
        "media_type": "collection"
        if is_collection(info)
        else info.get("media_type", "video"),
        "available_heights": sorted(
            {
                int(f["height"])
                for f in formats
                if f.get("height")
                and f.get("vcodec") != "none"
                and f.get("protocol")
                in ("http", "https", "m3u8_native", "http_dash_segments")
            },
            reverse=True,
        ),
    }


def extract(job, downloading=False):
    if job["platform"] not in ("threads", "facebook", "tiktok") and not any(
        c.IE_NAME != "generic" and c.suitable(job["url"])
        for c in gen_extractor_classes()
    ):
        raise ValueError("Unsupported URL")
    opts = options(job, downloading)
    with SafeDL(opts) as ydl:
        if job["platform"] == "instagram":
            from .instagram_media import InstagramMediaIE

            info = InstagramMediaIE(ydl).extract(job["url"])
            if info:
                info.update(extractor_key="Instagram", webpage_url=job["url"])
        elif job["platform"] == "x":
            from .social_media import TwitterMediaIE

            info = TwitterMediaIE(ydl).extract(job["url"])
        elif job["platform"] == "tiktok":
            from .social_media import TikTokMediaIE

            target = job["url"]
            if urlsplit(target).hostname in ("vm.tiktok.com", "vt.tiktok.com"):
                with ydl.urlopen(target) as response:
                    target = response.url
            info = TikTokMediaIE(ydl).extract(target)
        elif job["platform"] == "threads":
            from .social_media import extract_public_page

            info = extract_public_page(ydl, job["url"], "threads")
        elif job["platform"] == "facebook":
            from .social_media import extract_public_page

            try:
                info = extract_public_page(ydl, job["url"], "facebook")
            except ValueError as exc:
                if "MEDIA_DATA_UNAVAILABLE" not in str(exc):
                    raise
                # Existing video extractor still handles public Reels/video posts.
                if any(
                    x in job["url"]
                    for x in (
                        "/videos/",
                        "/reel/",
                        "/watch",
                        "fb.watch",
                        "/share/v/",
                        "/share/r/",
                    )
                ):
                    info = ydl.extract_info(job["url"], download=False)
                else:
                    raise
        else:
            info = ydl.extract_info(job["url"], download=False)
        if not info:
            raise ValueError("No video")

        def normalize_formats(item):
            for f in item.get("formats") or []:
                if not f.get("protocol") and urlsplit(f.get("url", "")).scheme in (
                    "https",
                    "http",
                ):
                    f["protocol"] = urlsplit(f["url"]).scheme
            for entry in item.get("entries") or []:
                if isinstance(entry, dict):
                    normalize_formats(entry)

        if job["platform"] in ("instagram", "x", "tiktok", "facebook", "threads"):
            normalize_formats(info)
        if job.get("entry_index") is not None:
            if not is_collection(info):
                if job["entry_index"] != 0:
                    raise ValueError("No video: collection changed")
            else:
                found = list(
                    islice(
                        info.get("entries") or [],
                        job["entry_index"],
                        job["entry_index"] + 1,
                    )
                )
                if not found or not found[0]:
                    raise ValueError("No video: collection changed")
                info = found[0]
        return info


def download(job, target, stem, progress):
    info = extract(job, True)
    if is_collection(info):
        raise ValueError("No video: review collection first")
    verify_media(info, job["mode"])
    if info.get("media_type") == "image":
        return download_image(job, info, target, stem, progress)
    if info.get("media_type") == "audio":
        job = {**job, "mode": "audio"}
    selected_height = job["options"].get("height")
    if job["mode"] == "video" and selected_height:
        formats = info.get("formats") or []
        if not any(
            f.get("height") == selected_height and f.get("vcodec") != "none"
            for f in formats
        ):
            raise ValueError("QUALITY_UNAVAILABLE")
        info["formats"] = [
            f
            for f in formats
            if f.get("vcodec") == "none" or f.get("height") == selected_height
        ]
    opts = options(job, True)
    opts["outtmpl"] = str(target / (stem.replace("%", "%%") + ".%(ext)s"))
    opts["postprocessors"] = (
        [{"key": "FFmpegExtractAudio", "preferredcodec": "best"}]
        if job["mode"] == "audio"
        else []
    )
    last = [0.0]

    def hook(data):
        downloaded = data.get("downloaded_bytes") or 0
        if downloaded > MAX_BYTES:
            raise ValueError("SIZE_LIMIT")
        if time.monotonic() - last[0] > 1 or data["status"] == "finished":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            progress(min(94, downloaded / total * 94) if total else 0)
            last[0] = time.monotonic()

    opts["progress_hooks"] = [hook]
    opts["postprocessor_hooks"] = [lambda d: progress(96)]
    with SafeDL(opts) as ydl:
        ydl.process_ie_result(info, download=True)
    media = [
        p
        for p in target.iterdir()
        if p.is_file()
        and p.suffix.lower()
        in (
            ".mp4",
            ".mkv",
            ".webm",
            ".mov",
            ".m4a",
            ".mp3",
            ".ogg",
            ".opus",
            ".flac",
            ".wav",
            ".aac",
        )
    ]
    if len(media) != 1:
        raise ValueError("No video: incomplete merge or download")
    if media[0].stat().st_size > MAX_BYTES:
        raise ValueError("SIZE_LIMIT")
    path = media[0]
    if job["mode"] == "video" and job["options"].get("output_format", "mp4") == "mp4":
        path = ensure_mp4(path, progress)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        timeout=30,
    )
    checked = json.loads(probe.stdout or "{}")
    streams = checked.get("streams", [])
    if probe.returncode or not streams:
        raise ValueError("No video: invalid downloaded file")
    meta = metadata(info)
    meta["duration"] = float(checked.get("format", {}).get("duration") or 0)
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    meta.update(
        width=video.get("width"),
        height=video.get("height"),
        max_height=video.get("height") or meta.get("max_height"),
    )
    meta["codecs"] = [s.get("codec_name") for s in streams]
    return path, meta


def download_image(job, info, target, stem, progress):
    from yt_dlp.networking import Request

    temporary = target / (stem + ".image-part")
    try:
        with (
            SafeDL(options(job)) as ydl,
            ydl.urlopen(
                Request(info["image_url"], headers={"Referer": job["url"]})
            ) as response,
            temporary.open("wb") as output,
        ):
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > min(MAX_BYTES, 64 * 1024**2):
                    raise ValueError("SIZE_LIMIT")
                output.write(chunk)
        with temporary.open("rb") as source:
            head = source.read(32)
        extension = (
            ".jpg"
            if head.startswith(b"\xff\xd8\xff")
            else ".png"
            if head.startswith(b"\x89PNG\r\n\x1a\n")
            else ".webp"
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP"
            else ".avif"
            if head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis")
            else None
        )
        if not extension:
            raise ValueError("No media: response is not an image")
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_streams",
                "-of",
                "json",
                str(temporary),
            ],
            capture_output=True,
            timeout=30,
        )
        streams = json.loads(probe.stdout or "{}").get("streams", [])
        if probe.returncode or not streams or not streams[0].get("width"):
            raise ValueError("No media: invalid image")
        path = target / (stem + extension)
        temporary.replace(path)
        progress(100)
        meta = metadata(info)
        meta.update(
            media_type="image",
            width=streams[0]["width"],
            height=streams[0]["height"],
            max_height=streams[0]["height"],
            available_heights=[],
            duration=None,
        )
        return path, meta
    finally:
        temporary.unlink(missing_ok=True)


def ensure_mp4(path, progress=lambda n: None):
    """Default is an H.264/AAC MP4 at the chosen resolution, with no 720p cap."""
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            timeout=30,
        )
    )
    streams = probe.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video:
        raise ValueError("No video")
    copy_video = video.get("codec_name") == "h264"
    copy_audio = not audio or audio.get("codec_name") == "aac"
    if path.suffix.lower() == ".mp4" and copy_video and copy_audio:
        return path
    output = path.with_name(path.stem + ".mp4-working.mp4")
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
    ]
    command += (
        ["-c:v", "copy"]
        if copy_video
        else [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        ]
    )
    command += ["-c:a", "copy"] if copy_audio else ["-c:a", "aac", "-b:a", "192k"]
    command += ["-movflags", "+faststart", str(output)]
    progress(97)
    try:
        result = subprocess.run(command, capture_output=True, timeout=6000)
        if result.returncode:
            raise ValueError("MP4_CONVERSION_FAILED")
        if output.stat().st_size > MAX_BYTES:
            raise ValueError("SIZE_LIMIT")
        destination = path.with_suffix(".mp4")
        path.unlink()
        output.replace(destination)
        return destination
    except BaseException:
        output.unlink(missing_ok=True)
        raise
