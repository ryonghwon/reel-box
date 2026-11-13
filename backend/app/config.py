import os
from pathlib import Path

DATA = Path(os.getenv("DATA_DIR", "/data"))
ROOT = Path(os.getenv("DOWNLOAD_ROOT", "/downloads")).resolve()
TOKEN = os.getenv("API_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MAX_BYTES = int(os.getenv("MAX_FILE_BYTES", str(4 * 1024**3)))
MIN_FREE = int(os.getenv("MIN_FREE_BYTES", str(1024**3)))
MAX_JOBS = max(2000, min(100000, int(os.getenv("MAX_JOBS", "50000"))))
WORKERS = max(1, min(6, int(os.getenv("REELBOX_WORKERS", "3"))))
DESKTOP = os.getenv("REELBOX_DESKTOP") == "1"
