# Reel Box

**내 컴퓨터에 보관하는 미디어 라이브러리.** Instagram 저장 목록과 여러 플랫폼의 링크에서 영상·이미지·오디오를 내려받고 관리하는 데스크톱 앱입니다.

Electron · Next.js / TypeScript · FastAPI / Python · yt-dlp · FFmpeg

![Reel Box 라이브러리](docs/screenshots/library.png)

> 소개 화면은 예시 데이터로 구성했습니다. 실제 사용자 썸네일, 라이브러리 개수, 계정, 저장 경로는 포함하지 않습니다.

## 주요 기능

- 여러 URL 일괄 등록, 중복 제거, 메타데이터와 썸네일 확인
- Instagram 공식 내보내기 ZIP / JSON / HTML에서 저장 목록 가져오기
- MP4 기본 저장, 최고 이용 가능 화질 또는 해상도 선택, 오디오 추출
- 영상은 개별 항목으로, 같은 게시물의 사진은 묶음으로 관리
- 카드 / 작은 썸네일 / 목록 보기, 검색, 상태 필터, 무한 스크롤
- 병렬 대기열, 오류 분류, 요청 제한 시 대기, 실패 재시도
- 개별 파일 / 선택 ZIP / 전체 ZIP / CSV 내보내기
- 저장 폴더 선택, 파일명 규칙, **자동 삭제 안 함** 기본값
- 사용자가 직접 선택한 화면 녹화

데스크톱 빌드는 자체 런타임과 로컬 대기열을 포함하므로 실행할 때 별도 Docker나 브라우저 서버를 켤 필요가 없습니다. 분석·AI API 호출·외부 AI 서비스 자동 업로드 기능은 없습니다.

## 지원 범위

| 플랫폼 | 구현 범위 | 확인이 필요한 부분 |
|---|---|---|
| Instagram | Reels, 영상, 사진, 혼합 게시물, 저장 목록, 앱 내 로그인 후 재시도 | 열람 권한·연령 확인·요청 제한에 따라 실패할 수 있음 |
| YouTube | 영상, Shorts, 오디오, 화질 선택, 선택적으로 재생목록·채널 | 재생목록/채널 한 번에 최대 100개; 채널 전체 다운로드 미검증 |
| Vimeo | 공개 영상, 오디오, 화질 선택 | 인증이 필요한 항목은 실패할 수 있음; 앱 내 로그인 연결 미구현 |
| TikTok | 영상, 사진 묶음, 제공되는 배경음 | 응답 구조 테스트와 실제 다운로드 성공 범위는 다름 |
| X | 영상, 사진, 혼합 첨부물, 오디오 | 로그인 제한 게시물 지원을 보장하지 않음 |
| Threads | 공개 게시물 첨부물 | 실제 다운로드 검증이 제한적 |
| Facebook | 공개 영상, 사진, 혼합 첨부물 | 그룹·권한 제한 페이지에 첨부물이 없으면 명시적으로 실패 |

일괄 지원을 보장하는 목록이 아닙니다. 사이트 변경, 삭제, 인증, 지역, 연령, 요청 제한, DRM 등에 따라 가용성이 달라집니다. 테스트 결과는 [검증 기록](docs/TESTING.md)을 참고하세요.

직접 이용 권한이 있는 콘텐츠만 저장하세요. 로그인은 앱 안의 공식 Instagram 화면에서 사용자가 직접 진행합니다. 외부 브라우저의 쿠키나 비밀번호를 추출하지 않으며, 세션은 앱 전용 프로필에 보관됩니다. 정상적으로 열람·재생할 수 있는 미디어를 처리하고 DRM이나 기술적 접근 제한을 우회하지 않습니다.

## 화면

<details>
<summary>Instagram 저장 목록 가져오기</summary>

![저장 목록 가져오기](docs/screenshots/saved-import.png)

</details>

<details>
<summary>저장 설정</summary>

![저장 설정](docs/screenshots/storage-settings.png)

</details>

## 소스에서 실행

이 저장소는 **소스 배포**입니다. 설치 파일과 Python·Node·FFmpeg 바이너리는 Git에 포함하지 않습니다. 기존 데스크톱 빌드 대상은 macOS Apple Silicon과 Windows x64이며, Windows 실기기 설치·실행은 아직 검증하지 않았습니다.

### 웹 개발 / Docker

Docker Compose를 사용할 수 있는 환경에서:

```sh
cp .env.example .env
# .env의 API_TOKEN을 충분히 긴 임의 값으로 변경
# DOWNLOAD_HOST_DIR에 다운로드를 저장할 로컬 폴더 지정

docker compose up --build
```

`http://localhost:3000`에서 실행합니다. 서버 모드는 FastAPI + Redis/RQ를 사용합니다. `.env`, DB, 다운로드 폴더는 Git에서 제외됩니다. 개발 서버는 개인용 로컬 실행을 전제로 합니다.

### 검사

Python 3.12, Node.js 24 계열을 사용한 프로젝트입니다. 백엔드 테스트에는 `ffmpeg`와 `ffprobe`가 PATH에 있어야 합니다.

```sh
cd backend
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check app
ruff format --check app tests

cd ../frontend
npm ci
npm run typecheck
npm test
npm run format:check

cd ../desktop
npm ci
npm test
```

Redis 통합 테스트는 별도 Redis가 없으면 생략됩니다. 자동 테스트는 사이트의 현재 다운로드 성공 여부를 증명하지 않습니다. 권한 있는 URL로 메타데이터만 확인하려면 `backend`에서 `python probe_platforms.py URL [URL ...]`을 실행하세요. 기본 샘플 URL은 제공하지 않습니다.

### 데스크톱 패키징

현재 패키징 스크립트는 **macOS Apple Silicon 빌드 호스트** 기준입니다. Windows 대상도 이 호스트에서 준비하는 방식이며, Windows 네이티브 빌드 환경은 별도로 정비해야 합니다.

1. Node.js / npm과 `uv`를 준비합니다.
2. Python 3.12.14 독립 런타임을 아래 위치에 준비합니다. 배포처는 [python-build-standalone](https://github.com/astral-sh/python-build-standalone)입니다.

```text
.build/python-runtimes/cpython-3.12.14-macos-aarch64-none/bin/python3
.build/python-runtimes/cpython-3.12.14-windows-x86_64-none/python.exe
```

3. 저장소 루트에서 실행합니다.

```sh
npm ci --prefix frontend
npm ci --prefix desktop
npm run build:web --prefix desktop
npm run prepare:mac --prefix desktop
npm run build:mac --prefix desktop

# Windows x64 대상
npm run prepare:win --prefix desktop
npm run build:win --prefix desktop
```

`REELBOX_BUILD_WORK` 환경 변수로 `.build` 위치를 바꿀 수 있습니다. 산출물은 `desktop/release/`에 생성됩니다. macOS 공증과 Windows 배포 인증서 서명은 별도이며, 공개 바이너리를 배포하려면 제3자 런타임의 라이선스와 소스 제공 조건도 확인해야 합니다. 사용한 런타임 정보는 `docs/runtime-*.json`에 있습니다.

## 데이터 보관

미디어는 선택한 로컬 폴더에 파일로 저장하고 앱은 SQLite에 목록·출처·진행 상태를 관리합니다. 기본 미디어 위치는 macOS의 `~/Movies/Reelbox Library/Reelbox`, Windows의 사용자 Videos 폴더 아래 `Reelbox Library/Reelbox`입니다. 데이터와 세션 프로필 이름은 호환성을 위해 `reelbox-desktop`을 유지합니다.

저장 폴더 변경은 새로 등록하는 항목부터 적용되며 기존 파일은 원래 위치에서 유지됩니다. 파일을 직접 옮기면 앱에서 찾지 못할 수 있으므로 사본은 **다른 위치에 저장**을 사용하세요. 자동 삭제를 설정하지 않으면 직접 삭제할 때까지 보관합니다.

## 구조

```text
frontend/app/       라이브러리, 가져오기, 상세 패널, 설정
backend/app/        API, 작업 대기열, 추출, 저장, 중복 연결
desktop/           Electron 앱, 로그인 창, 패키징 스크립트
docs/              공개용 화면과 검증 범위
```

기여 시 실제 계정, 쿠키, 내보내기 파일, 개인 게시물 링크나 다운로드 기록을 커밋하지 마세요. 테스트에는 가상 데이터를 사용합니다.

## 라이선스

애플리케이션 코드는 [MIT](LICENSE)입니다. 플랫폼 로고의 상표권과 각 종속성의 라이선스는 해당 소유자에게 있습니다. FFmpeg 등 별도 런타임에는 다른 라이선스가 적용됩니다. [제3자 고지](desktop/THIRD-PARTY-NOTICES.txt)를 참고하세요.
