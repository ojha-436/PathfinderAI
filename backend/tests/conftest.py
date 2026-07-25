"""Test setup — deterministic, DB-isolated, no external services.

Env is set BEFORE any app import so config/database pick it up: a throwaway
sqlite file, a fixed JWT secret, and Gemini disabled (so resolve/roadmap use
the deterministic local paths and tests are reproducible).
"""
import os
import pathlib
import tempfile

os.environ.pop("GEMINI_API_KEY", None)
os.environ["GEMINI_JD_PARSE"] = "False"
os.environ["JWT_SECRET"] = "test-secret-not-for-prod"
_DB = pathlib.Path(tempfile.gettempdir()) / "pf_test.db"
if _DB.exists():
    _DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app  # imported after env is set; create_all runs on import
    with TestClient(app) as c:
        yield c
