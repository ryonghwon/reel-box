import ipaddress
import re
import socket
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


class InvalidURL(ValueError):
    pass


def normalize(value: str, collections=False):
    value = value.strip()
    if len(value) > 2048 or any(ord(x) < 32 for x in value):
        raise InvalidURL("URL 길이나 문자가 올바르지 않습니다.")
    try:
        p = urlsplit(value)
        if (
            p.scheme not in ("http", "https")
            or p.username
            or p.password
            or p.port not in (None, 80, 443)
        ):
            raise InvalidURL(
                "인증 정보나 사용자 지정 포트가 없는 HTTPS 링크를 입력하세요."
            )
        host = (p.hostname or "").lower()
    except ValueError as e:
        raise InvalidURL("올바른 URL을 입력하세요.") from e
    path = p.path.rstrip("/") or "/"
    q = parse_qs(p.query)
    query = {}
    if host in ("instagram.com", "www.instagram.com", "m.instagram.com"):
        m = re.fullmatch(
            r"/(?:[A-Za-z0-9_.]+/)?(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)", path
        )
        if not m:
            raise InvalidURL(
                "Instagram Reels 또는 영상 게시물의 개별 링크를 입력하세요."
            )
        host = "www.instagram.com"
        path = "/p/" + m[1] + "/"
        platform = "instagram"
    elif host in (
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "www.youtu.be",
    ):
        platform = "youtube"
        host_in = host
        host = "www.youtube.com"
        video = (
            path.lstrip("/")
            if "youtu.be" == host_in.removeprefix("www.")
            else q.get("v", [""])[0]
        )
        short = re.fullmatch(r"/(?:shorts|embed|live)/([\w-]{11})", path)
        if short:
            video = short[1]
        if video:
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
                raise InvalidURL("YouTube 영상 ID를 확인하세요.")
            path = "/watch"
            query = {"v": video}
        elif (
            collections
            and path == "/playlist"
            and re.fullmatch(r"[\w-]+", q.get("list", [""])[0])
        ):
            query = {"list": q["list"][0]}
        elif collections and re.fullmatch(
            r"/(?:@[\w.\-]+|channel/[\w-]+|c/[\w-]+|user/[\w-]+)(?:/(?:videos|shorts))?",
            path,
        ):
            if not path.endswith(("/videos", "/shorts")):
                path += "/videos"
        else:
            raise InvalidURL(
                "재생목록·채널은 컬렉션 허용을 켜세요. 또는 개별 영상 링크를 입력하세요."
            )
    elif host in ("vimeo.com", "www.vimeo.com", "player.vimeo.com"):
        platform = "vimeo"
        if not re.fullmatch(r"/(?:video/)?\d+(?:/[a-fA-F0-9]+)?", path):
            raise InvalidURL("Vimeo 개별 영상 링크를 입력하세요.")
        host = "vimeo.com"
        path = path.removeprefix("/video")
        if "h" in q:
            query["h"] = q["h"][0]
    elif host in (
        "tiktok.com",
        "www.tiktok.com",
        "m.tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
    ):
        platform = "tiktok"
        if not (
            re.fullmatch(r"/@[^/]+/(?:video|photo)/\d+", path)
            or (
                host in ("vm.tiktok.com", "vt.tiktok.com")
                and re.fullmatch(r"/[\w-]+", path)
            )
        ):
            raise InvalidURL("TikTok 영상 링크를 입력하세요.")
        if host not in ("vm.tiktok.com", "vt.tiktok.com"):
            host = "www.tiktok.com"
        else:
            path += "/"
    elif host in (
        "x.com",
        "www.x.com",
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
    ):
        platform = "x"
        host = "x.com"
        m = re.fullmatch(
            r"/(?:[^/]+/status|i/status)/(\d+)(?:/(?:video|photo)/\d+)?", path
        )
        if not m:
            raise InvalidURL("X 개별 게시물 링크를 입력하세요.")
        path = "/i/status/" + m[1]
    elif host in ("threads.net", "www.threads.net", "threads.com", "www.threads.com"):
        platform = "threads"
        host = "www.threads.com"
        if not re.fullmatch(r"/@[^/]+/post/[\w-]+", path):
            raise InvalidURL("Threads 개별 게시물 링크를 입력하세요.")
    elif host in (
        "facebook.com",
        "www.facebook.com",
        "m.facebook.com",
        "web.facebook.com",
        "fb.watch",
    ):
        platform = "facebook"
        if host == "fb.watch":
            if not re.fullmatch(r"/[\w-]+", path):
                raise InvalidURL("Facebook 영상 링크를 확인하세요.")
            path += "/"
        else:
            host = "www.facebook.com"
            if path in ("/watch", "/video.php") and q.get("v", [""])[0].isdigit():
                query = {"v": q["v"][0]}
                path = "/watch/"
            elif path in ("/photo", "/photo.php") and q.get("fbid", [""])[0].isdigit():
                query = {"fbid": q["fbid"][0]}
                path = "/photo/"
            elif (
                path in ("/permalink.php", "/story.php")
                and q.get("story_fbid", [""])[0].isdigit()
                and q.get("id", [""])[0].isdigit()
            ):
                query = {"story_fbid": q["story_fbid"][0], "id": q["id"][0]}
            elif not re.fullmatch(
                r"/(?:reel/\d+|[^/]+/videos/(?:[^/]+/)?\d+|share/(?:[rvp]/)?[\w-]+|[^/]+/posts/[\w-]+|groups/[\w.-]+/(?:posts|permalink)/\d+|[^/]+/photos/(?:[^/]+/)*\d+)",
                path,
            ):
                raise InvalidURL("Facebook 개별 게시물·사진·영상 링크를 입력하세요.")
    else:
        raise InvalidURL("지원 플랫폼의 영상 URL만 등록할 수 있습니다.")
    return urlunsplit(("https", host, path, urlencode(query), "")), platform


def assert_public_url(url):
    """Also applied to extractor HTTP requests and redirects; no local resource fetching."""
    p = urlsplit(url)
    if (
        p.scheme not in ("http", "https")
        or not p.hostname
        or p.username
        or p.password
        or p.port not in (None, 80, 443)
    ):
        raise InvalidURL("허용하지 않는 미디어 주소입니다.")
    addresses = socket.getaddrinfo(
        p.hostname,
        p.port or (443 if p.scheme == "https" else 80),
        type=socket.SOCK_STREAM,
    )
    if not addresses or any(
        not ipaddress.ip_address(x[4][0]).is_global for x in addresses
    ):
        raise InvalidURL("내부 네트워크 주소에는 연결할 수 없습니다.")
