import os
import tempfile

# Must be set before the app is imported: settings are read once at import time.
_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["APP_ENV"] = "development"
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"  # unreachable on purpose: forces the in-memory fallback

import pytest
from fastapi.testclient import TestClient

import main
from database.session import init_db


@pytest.fixture(scope="session")
def client():
    init_db()
    return TestClient(main.app)
