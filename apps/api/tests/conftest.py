from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in os.sys.path:
    os.sys.path.insert(0, str(API_DIR))


@pytest.fixture(scope="session", autouse=True)
def test_environment(tmp_path_factory: pytest.TempPathFactory) -> None:
    data_dir = tmp_path_factory.mktemp("retainai-api")
    db_path = data_dir / "retainai-test.db"
    artifact_dir = data_dir / "artifacts"
    mlruns_dir = data_dir / "mlruns"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    mlruns_dir.mkdir(parents=True, exist_ok=True)

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["MODEL_ARTIFACT_DIR"] = str(artifact_dir)
    os.environ["MLFLOW_TRACKING_URI"] = f"file:///{mlruns_dir.as_posix()}"
    os.environ["AUTO_SEED"] = "true"
    os.environ["SEED_USER_PASSWORD"] = "retainai-demo"
    os.environ["ENVIRONMENT"] = "test"

    from app.core.config import get_settings
    from app.db import reset_db_connection

    get_settings.cache_clear()
    reset_db_connection()


@pytest.fixture()
def client() -> TestClient:
    from app.db import Base, get_engine
    from app.main import app

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@retainai.local", "password": "retainai-demo"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
