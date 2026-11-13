import os
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="reelbox-test-db-")
os.environ["DOWNLOAD_ROOT"] = tempfile.mkdtemp(prefix="reelbox-test-files-")
os.environ["API_TOKEN"] = "test-token-only-12345678901234567890"
os.environ["MIN_FREE_BYTES"] = "0"
import pytest
from fastapi.testclient import TestClient
from app import db
from app.main import app
from app.config import TOKEN


@pytest.fixture(autouse=True)
def clear_db():
    db.init()
    with db.connect() as c:
        c.execute("DELETE FROM platform_cooldowns")
        c.execute("DELETE FROM import_drafts")
        c.execute("DELETE FROM exports")
        c.execute("DELETE FROM files")
        c.execute("DELETE FROM jobs")
        c.execute("DELETE FROM settings")
    db.init()


@pytest.fixture
def client():
    with TestClient(app, headers={"X-API-Key": TOKEN}) as client:
        yield client
