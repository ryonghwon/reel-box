# Build and run

## Runtime options

| Distribution | Requirements | Startup |
| --- | --- | --- |
| Desktop package | Apple Silicon macOS or Windows x64 | The app starts its local service and queue automatically |
| Docker | Docker Engine/Desktop and Compose v2 | Open the local web interface after starting the services |

Source control contains application code and packaging configuration. Runtime binaries and installers are distributed as release assets, not committed to Git.

## Run with Docker

On macOS or Linux, run from the repository root:

```sh
sh scripts/setup.sh
docker compose up --build -d
```

On Windows, run Docker Desktop in Linux-container mode and open `Start-Reelbox.cmd`. Setup creates `.env` on first use and leaves an existing file intact.

Open [localhost:3000](http://localhost:3000), or the configured `WEB_PORT`. Services bind to local interfaces. Hosting for other users requires a separate authentication and access-control design.

```sh
docker compose ps
docker compose logs --tail=100 api worker web
docker compose down
```

`down` stops containers and preserves volumes. `down -v` deletes data volumes and is not a normal shutdown command. Keep the API, workers, maintenance, and Redis services running while the queue is processing.

## Build desktop packages

The packaging workflow uses an Apple Silicon Mac with Node.js 24, npm, uv, and standalone Python 3.12.14 runtimes. Mac arm64 and Windows x64 packages are produced from the same source. Preparing the Windows payload also requires the host Mac Python runtime.

Place the appropriate [python-build-standalone](https://github.com/astral-sh/python-build-standalone) distributions at:

```text
.build/python-runtimes/cpython-3.12.14-macos-aarch64-none/bin/python3
.build/python-runtimes/cpython-3.12.14-windows-x86_64-none/python.exe
```

Set `REELBOX_BUILD_WORK` to use a different build-cache directory. From the repository root:

```sh
npm ci --prefix frontend
npm ci --prefix desktop
npm run build:web --prefix desktop

npm run prepare:mac --prefix desktop
npm run build:mac --prefix desktop

npm run prepare:win --prefix desktop
npm run build:win --prefix desktop
```

The preparation step installs target-specific Python packages and stages Node.js, FFmpeg, and FFprobe. It needs network access and enough space for downloaded and extracted runtimes. The web build stages a static export without the server-only API proxy; the desktop service handles those routes.

Packages are written to `desktop/release/`:

- `Reel-Box-<version>-macOS-arm64.zip`
- `Reel-Box-<version>-Windows-x64-Setup.exe`

The default configuration ad-hoc signs Mac bundles and leaves Windows packages unsigned. Mac builds are not notarized. Configure Developer ID signing and notarization or Windows code signing in the distribution environment when certificates are available. Include [third-party notices](../desktop/THIRD-PARTY-NOTICES.txt) and satisfy the license and source-distribution requirements of bundled runtimes.

## Validate source

Use Python 3.12 and put FFmpeg/FFprobe on `PATH`.

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

Tests use temporary databases, files, and fixed inputs. Set `TEST_REDIS_URL` to a dedicated test Redis instance to run Redis integration checks. Never point these tests at a user library or a production queue.

To inspect extraction for content you are authorized to access, run from `backend`:

```sh
python probe_platforms.py URL [URL ...]
```

This probe checks metadata without downloading the media. Platform responses can change independently of an app build; a successful probe is specific to the tested URL and environment.

## Release checks

Verify that the desktop package version, web package version, API version, tag, and asset names agree. Build from the intended source commit, generate SHA-256 checksums, and verify uploaded assets against those checksums.

On each target operating system, check startup and shutdown, folder selection, a download, recovery after restart, and playback. A successful cross-platform package build alone does not establish runtime compatibility on that system. Publish target-specific validation results alongside the release when applicable.

Verify the final Mac archive after packaging:

```sh
node desktop/scripts/verify-mac.cjs desktop/release/Reel-Box-0.1.0-macOS-arm64.zip
```

The check extracts a temporary copy, verifies the archive and complete code signature, and checks executable permissions. It does not certify notarization. CI runs backend tests with Redis, frontend checks, desktop unit tests, and the static web build.
