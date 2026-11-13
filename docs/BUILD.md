# 설치와 빌드

## 실행 구성

| 구성 | 필요한 환경 | 실행 방식 |
| --- | --- | --- |
| 데스크톱 패키지 | macOS Apple Silicon 또는 Windows x64 | 앱이 로컬 서버와 대기열을 함께 실행 |
| Docker | Docker Engine/Desktop, Compose v2 | 로컬 브라우저에서 사용 |

이 저장소에는 소스와 패키징 설정을 제공합니다. Python, Node.js, FFmpeg 런타임과 설치 파일은 Git 소스에 포함하지 않습니다.

## Docker

macOS와 Linux에서는 저장소 루트에서 실행합니다.

```sh
sh scripts/setup.sh
docker compose up --build -d
```

Windows에서는 Docker Desktop을 Linux 컨테이너 모드로 실행하고 `Start-Reelbox.cmd`를 엽니다. 설정 파일은 첫 실행 때 생성됩니다. 기존 `.env`는 덮어쓰지 않습니다.

기본 주소는 [localhost:3000](http://localhost:3000)입니다. 서비스는 로컬 인터페이스에만 공개됩니다. 다른 사용자에게 공개하는 서버 구성에는 별도의 사용자 인증과 접근 제어가 필요합니다.

```sh
docker compose ps
docker compose logs --tail=100 api worker web
docker compose down
```

`down`은 컨테이너를 종료하고 볼륨은 유지합니다. `down -v`는 데이터 볼륨을 삭제하므로 일반 종료에는 사용하지 않습니다. 작업 대기열을 계속 처리하려면 API, worker, maintenance, Redis 서비스를 실행해 둡니다.

## 데스크톱 빌드

빌드 호스트는 macOS Apple Silicon입니다. Node.js 24, npm, uv, Python 3.12.14 독립 런타임을 준비합니다. macOS와 Windows 패키지는 동일한 소스에서 각각 생성합니다.

Python 런타임은 [python-build-standalone](https://github.com/astral-sh/python-build-standalone) 배포본을 다음 위치에 준비합니다. Windows 패키징에도 호스트용 macOS Python이 필요합니다.

```text
.build/python-runtimes/cpython-3.12.14-macos-aarch64-none/bin/python3
.build/python-runtimes/cpython-3.12.14-windows-x86_64-none/python.exe
```

`REELBOX_BUILD_WORK`로 `.build` 위치를 변경할 수 있습니다. 저장소 루트에서 실행합니다.

```sh
npm ci --prefix frontend
npm ci --prefix desktop
npm run build:web --prefix desktop

npm run prepare:mac --prefix desktop
npm run build:mac --prefix desktop

npm run prepare:win --prefix desktop
npm run build:win --prefix desktop
```

런타임 준비 단계는 대상 운영체제의 Python 패키지, Node.js, FFmpeg, FFprobe를 내려받고 패키징 폴더에 배치합니다. 네트워크 연결과 압축 해제 공간이 필요합니다. 산출물은 `desktop/release/`에 생성됩니다.

기본 빌드는 서명·공증을 적용하지 않습니다. 외부 배포 시 macOS Developer ID 서명과 공증, Windows 코드 서명을 배포 환경에 맞게 구성합니다. [제3자 고지](../desktop/THIRD-PARTY-NOTICES.txt)와 런타임별 라이선스·소스 제공 조건도 배포물에 반영합니다.

## 코드 검사

Python 3.12와 FFmpeg/FFprobe가 PATH에 있어야 합니다.

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
npm run build:web
```

테스트는 임시 데이터베이스, 임시 파일과 고정 입력 데이터를 사용합니다. Redis 통합 검사는 `TEST_REDIS_URL`로 별도의 테스트 Redis를 지정합니다. 테스트용 Redis에는 사용자 데이터를 넣지 않습니다.

플랫폼 응답을 확인하려면 `backend`에서 이용 권한이 있는 링크를 직접 전달합니다. 이 명령은 메타데이터만 확인합니다.

```sh
python probe_platforms.py URL [URL ...]
```

패키지를 배포하기 전에 대상 운영체제에서 앱 시작·종료, 저장 폴더 선택, 다운로드, 재시작 후 작업 복구, 파일 재생을 확인합니다.
