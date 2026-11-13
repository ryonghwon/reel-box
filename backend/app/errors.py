import re


def classify(exc):
    text = str(exc).lower()
    if "storage_unavailable" in text:
        return (
            "STORAGE_UNAVAILABLE",
            "저장 폴더를 찾을 수 없습니다. 디스크 연결을 확인한 뒤 다시 시도하세요.",
            True,
        )
    if "drm" in text:
        return "DRM_PROTECTED", "DRM으로 보호된 영상은 다운로드하지 않습니다.", False
    if "instagram sent an empty media response" in text:
        return (
            "MEDIA_DATA_UNAVAILABLE",
            "Instagram의 응답에 원본 미디어가 없습니다. 로그인 필요 여부는 이 응답만으로 확정할 수 없습니다. 로그인 창에서 정상적으로 게시물을 연 뒤 저장해 보세요.",
            True,
        )
    if any(
        t in text
        for t in (
            "age-restricted",
            "age restricted",
            "age verification",
            "verify your age",
            "confirm your age",
            "minimum age",
            "연령 확인",
            "연령 제한",
        )
    ):
        return (
            "AGE_RESTRICTED",
            "플랫폼이 연령 확인을 요구했습니다. 공식 사이트에서 본인 계정으로 연령 확인을 완료하고, 정상적으로 열람되는 게시물만 로그인 창에서 저장할 수 있습니다.",
            False,
        )
    if any(
        t in text
        for t in (
            "isn't available to everyone",
            "certain audiences",
            "restricted video",
        )
    ):
        return (
            "AUDIENCE_RESTRICTED",
            "Instagram이 이 게시물의 열람 대상을 제한하고 있습니다. 연령·계정·지역 중 어떤 조건인지는 확인되지 않았습니다. 본인 계정으로 정상 열람되는 경우 로그인 창에서 저장해 보세요.",
            False,
        )
    if re.search(
        r"\b(?:http(?: error)?[: ]+429|too many requests|rate[- ]limit)", text
    ):
        return "RATE_LIMITED", "플랫폼 요청 제한입니다. 잠시 후 다시 시도하세요.", True
    if "media_data_unavailable" in text:
        return (
            "MEDIA_DATA_UNAVAILABLE",
            "공개 응답에 게시물 원본 미디어가 제공되지 않았습니다. 로그인 필요 또는 페이지 형식 변경일 수 있습니다. 링크 미리보기 이미지를 원본으로 대신 저장하지 않습니다.",
            False,
        )
    if "quality_unavailable" in text:
        return (
            "QUALITY_UNAVAILABLE",
            "선택한 해상도가 더 이상 제공되지 않습니다. 링크를 다시 확인하고 다른 화질을 선택하세요.",
            False,
        )
    if "mp4_conversion_failed" in text:
        return (
            "MP4_CONVERSION_FAILED",
            "MP4 변환에 실패했습니다. 원본 형식으로 다시 등록하거나 재시도하세요.",
            True,
        )
    if "job_limit" in text:
        return (
            "JOB_LIMIT",
            "보관함의 작업 한도에 도달했습니다. 기록 한도를 늘리거나 기존 기록을 정리한 뒤 다시 시도하세요.",
            True,
        )
    if "[vimeo]" in text and "web client only works when logged-in" in text:
        return (
            "AUTH_REQUIRED",
            "현재 Vimeo 추출 방식에는 로그인이 필요합니다. 이 앱은 Vimeo 계정 연동을 지원하지 않아 브라우저 로그인만으로 해결되지 않습니다. 원본 페이지의 다운로드 기능을 확인하세요.",
            False,
        )
    if any(
        t in text
        for t in (
            "login",
            "log in",
            "sign in",
            "cookies",
            "private video",
            "private account",
            "authentication",
        )
    ):
        return (
            "AUTH_REQUIRED",
            "플랫폼 로그인이 필요합니다. 외부 브라우저 로그인은 자동 연결되지 않습니다. Instagram은 앱의 로그인 창에서 정상 열람 후 저장을 시도할 수 있습니다. 다른 플랫폼은 원본 사이트의 다운로드 기능을 확인하세요.",
            False,
        )
    if any(
        t in text
        for t in (
            "403",
            "forbidden",
            "captcha",
            "challenge",
            "bot",
            "access denied",
            "blocked",
        )
    ):
        return (
            "ACCESS_RESTRICTED",
            "플랫폼이 자동 접근을 제한했습니다. 정상 재생 가능한 영상은 화면 녹화를 이용하세요.",
            False,
        )
    if any(t in text for t in ("geo", "not available in your country")):
        return "REGION_RESTRICTED", "현재 지역에서는 제공되지 않습니다.", False
    if any(
        t in text
        for t in ("404", "not found", "unavailable", "removed", "does not exist")
    ):
        return "UNAVAILABLE", "삭제되었거나 현재 이용할 수 없는 게시물입니다.", False
    if any(
        t in text for t in ("no video", "no formats", "only images", "requested format")
    ):
        return "NO_MEDIA", "이 모드로 다운로드할 수 있는 영상·오디오가 없습니다.", False
    if "unsupported url" in text:
        return (
            "EXTRACTOR_UNSUPPORTED",
            "설치된 추출기가 이 링크를 지원하지 않습니다.",
            False,
        )
    if any(t in text for t in ("disk_full", "no space left")):
        return "DISK_FULL", "저장 공간이 부족합니다. 여유 공간을 확보하세요.", True
    if any(t in text for t in ("size_limit", "file is larger", "max-filesize")):
        return "SIZE_LIMIT", "파일 크기 제한을 초과했습니다.", False
    if any(
        t in text
        for t in (
            "timed out",
            "timeout",
            "connection",
            "network",
            "resolve",
            "503",
            "502",
        )
    ):
        return (
            "NETWORK_ERROR",
            "네트워크 연결에 실패했습니다. 연결 상태를 확인하고 다시 시도하세요.",
            True,
        )
    if "live_unsupported" in text:
        return "LIVE_UNSUPPORTED", "진행 중인 라이브 영상은 지원하지 않습니다.", False
    return (
        "EXTRACTION_FAILED",
        "추출에 실패했습니다. 게시물 상태와 추출기 업데이트를 확인하세요.",
        True,
    )
