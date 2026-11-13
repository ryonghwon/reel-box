# Architecture

## Runtime paths

The desktop app uses Electron to start a FastAPI service on a random loopback port and display the bundled static interface. Python, Node.js, FFmpeg, and FFprobe are packaged with the app. The service and local worker processes stop when the app exits; persisted queue state is recovered on the next launch.

The Docker configuration uses Next.js to forward API requests to FastAPI. Redis/RQ workers run download jobs, while the maintenance service handles queue recovery and file retention. Both runtimes share the media pipeline and SQLite data model.

## Module boundaries

| Module | Responsibility |
| --- | --- |
| `frontend/app/page.tsx` | Navigation and user actions |
| `frontend/app/use-library-sync.ts` | Polling, status updates, and incremental task merging |
| `frontend/app/library.ts` | Image grouping and selection expansion |
| `frontend/app/media.ts` | Shared media types, labels, and display formatting |
| `frontend/app/api-client.ts` | API requests and error handling |
| `backend/app/main.py` | Service lifecycle and request authentication |
| `backend/app/routes/` | Tasks, settings, imports, exports, recordings, and browser saves |
| `backend/app/schemas.py` | Request validation |
| `backend/app/job_listing.py` | Task and file snapshots |
| `backend/app/tasks.py` | Metadata and download jobs |
| `backend/app/extractor.py` | Platform extraction and media processing |
| `backend/app/storage.py` | Paths, filenames, and storage checks |
| `backend/app/db.py` | SQLite persistence and migrations |
| `desktop/browser-*.cjs` | Instagram window, attachment matching, and signed-in batches |

## Tasks and files

URLs are normalized before deduplication with platform and download mode. Multi-attachment posts retain a parent/child relationship in storage. The interface groups image attachments by post and leaves videos as individual items.

Each task records its storage settings when it is added. Changing the global folder does not relocate existing tasks. Disabling retention removes scheduled deletion dates from existing files.

The synchronization API returns changed tasks alongside current task IDs. The interface merges updates and removes IDs no longer present. ZIP exports use a fixed snapshot of selected files and read them sequentially, avoiding a large number of simultaneously open file handles.

## Authentication and network access

The desktop service uses a new internal authentication value for each launch. Docker uses the shared `API_TOKEN` from the service environment. These values protect local service calls and are separate from social-platform credentials.

Instagram sessions are kept in an app-specific browser profile. Users sign in on the official site; the app does not read account credentials from external browser profiles. Media handling is limited to content accessible in that session. Platform extraction requests are restricted to allowed public network destinations.

## Public assets

Product guides use illustrated interfaces and example data. User libraries, export archives, databases, cookies, logs, and generated runtime packages are excluded from source control. Release binaries contain application code and required runtimes, not local library state.
