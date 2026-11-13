"""Read a user-provided Instagram export without extracting files or retaining it."""

import io
import json
import re
import zipfile
import zlib
from html.parser import HTMLParser
from pathlib import PurePosixPath

from .urls import normalize

UPLOAD_LIMIT = 32 * 1024**2
TEXT_LIMIT = 64 * 1024**2
URL_LIMIT = 20000
SAVED_FILE = re.compile(
    r"saved(?:_posts|_collections|_media)?(?:_\d+)?\.(?:json|html?)$", re.I
)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.values.extend(v for k, v in attrs if k == "href" and v)


def strings(value):
    # Iteration avoids recursive traversal of an untrusted, deeply nested export.
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            pending.extend(reversed(list(item.values())))
        elif isinstance(item, list):
            pending.extend(reversed(item))


def parse_export(raw: bytes, filename: str):
    if len(raw) > UPLOAD_LIMIT:
        raise ValueError(
            "32MB 이하의 파일을 선택하세요. 큰 ZIP은 압축을 풀고 saved_posts.json 또는 HTML만 가져오세요."
        )
    documents = []
    try:
        if filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                if len(entries) > 10000:
                    raise ValueError(
                        "ZIP 안에 파일이 너무 많습니다. saved_posts 파일만 선택하세요."
                    )
                chosen = [
                    e
                    for e in entries
                    if not e.is_dir()
                    and SAVED_FILE.fullmatch(PurePosixPath(e.filename).name)
                ]
                if not chosen:
                    raise ValueError(
                        "저장 목록 파일을 찾지 못했습니다. 계정 내보내기에서 저장됨(Saved)을 선택하세요."
                    )
                if sum(e.file_size for e in chosen) > TEXT_LIMIT:
                    raise ValueError("저장 목록의 압축 해제 크기가 64MB를 초과합니다.")
                for entry in chosen:
                    if entry.flag_bits & 1:
                        raise ValueError(
                            "암호화된 ZIP은 지원하지 않습니다. 저장 목록 파일만 선택하세요."
                        )
                    # No extract(): paths, executable files and unrelated account data are ignored.
                    with archive.open(entry) as stream:
                        data = stream.read(TEXT_LIMIT + 1)
                    if len(data) > TEXT_LIMIT:
                        raise ValueError("저장 목록 파일이 너무 큽니다.")
                    documents.append((PurePosixPath(entry.filename).name, data))
        elif SAVED_FILE.fullmatch(PurePosixPath(filename).name):
            documents = [(filename, raw)]
        else:
            raise ValueError(
                "Instagram 내보내기의 ZIP 또는 saved_posts / saved_collections JSON·HTML 파일을 선택하세요."
            )

        urls = []
        seen = set()
        duplicates = 0
        ignored = 0
        for name, data in documents:
            text = data.decode("utf-8-sig")
            if name.lower().endswith(".json"):
                values = strings(json.loads(text))
            else:
                parser = Links()
                parser.feed(text)
                values = parser.values
            for value in values:
                if not value.startswith(("http://", "https://")):
                    continue
                try:
                    url, platform = normalize(value)
                    if platform != "instagram":
                        raise ValueError("Not Instagram")
                except ValueError:
                    ignored += 1
                    continue
                if url in seen:
                    duplicates += 1
                    continue
                seen.add(url)
                urls.append(url)
                if len(urls) > URL_LIMIT:
                    raise ValueError(
                        "저장 목록은 한 번에 20,000개 링크까지 읽을 수 있습니다. 파일을 나누어 가져오세요."
                    )
    except (
        zipfile.BadZipFile,
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        RuntimeError,
        NotImplementedError,
        zlib.error,
        EOFError,
    ) as exc:
        raise ValueError(
            "파일 형식을 읽을 수 없습니다. Instagram에서 받은 원본 ZIP·JSON·HTML인지 확인하세요."
        ) from exc
    if not urls:
        raise ValueError(
            "저장된 게시물 링크를 찾지 못했습니다. 저장됨(Saved) 항목과 전체 기간으로 내보냈는지 확인하세요."
        )
    return {
        "urls": urls,
        "duplicates": duplicates,
        "ignored": ignored,
        "files": [name for name, _ in documents],
    }
