import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

temp_root = Path(tempfile.mkdtemp(prefix="catforge-tests-"))
os.environ["CATFORGE_DATABASE_URL"] = f"sqlite:///{temp_root / 'test.db'}"
os.environ["CATFORGE_UPLOAD_DIR"] = str(temp_root / "uploads")
os.environ["CATFORGE_EXPORT_DIR"] = str(temp_root / "exports")

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]

