import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def test_db_env(monkeypatch, tmp_path):
    """Isolate database and backups in a temporary directory for tests."""
    temp_data_dir = tmp_path / "data"
    temp_data_dir.mkdir(parents=True, exist_ok=True)
    temp_db_path = temp_data_dir / "test_habits.db"
    temp_backup_dir = temp_data_dir / "backups"
    temp_backup_dir.mkdir(parents=True, exist_ok=True)

    from backend import config, database
    monkeypatch.setattr(config, "DATA_DIR", temp_data_dir)
    monkeypatch.setattr(config, "DB_PATH", temp_db_path)
    monkeypatch.setattr(config, "BACKUP_DIR", temp_backup_dir)

    # Initialize tables and seed default users & tasks
    database.init_db()

    yield temp_db_path


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Reset process-global mutable state so tests cannot leak into each other.

    - the mock clock (`clock.set_mock_time`) is module-level on purpose;
    - the login rate limiter keeps IP/pair attempt history in memory.
    """
    from backend import clock
    from backend.routers import auth_router

    clock.set_mock_time(None)
    auth_router.limiter._attempts.clear()
    yield
    clock.set_mock_time(None)
    auth_router.limiter._attempts.clear()


@pytest.fixture
def client(test_db_env):
    from backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def parent_client(client):
    # Default parent is tayhe / parents
    resp = client.post("/api/v1/auth/login", json={"username": "tayhe", "password": "parents"})
    assert resp.status_code == 200
    return client


@pytest.fixture
def child_client(client):
    # Default child is meow / child
    resp = client.post("/api/v1/auth/login", json={"username": "meow", "password": "child"})
    assert resp.status_code == 200
    return client
