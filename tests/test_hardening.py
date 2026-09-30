"""Hardening / contract tests added in the fix-mimo 复检 round (§6.4).

Covers the gaps the original suite had no test for:
- API surface hardening (docs off, security headers, CORS off)
- child × tasks CRUD (permission matrix)
- TaskCreate required fields (N-02)
- login rate limit end-to-end (429 over HTTP)
- seed credentials come from config (env-overridable) and DB_PATH has a single source
"""

from fastapi.testclient import TestClient

from backend import config, database

# --- API surface hardening (Phase 3.5) --------------------------------------

def test_api_docs_disabled_by_default(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_security_headers_on_every_response(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "same-origin"
    csp = resp.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp

    # Static frontend responses are hardened too.
    page = client.get("/")
    assert page.headers["X-Content-Type-Options"] == "nosniff"


def test_cors_is_disabled_by_default(client):
    """The SPA is same-origin; no cross-origin browser request is legitimate."""
    resp = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers


# --- Permission matrix: child x tasks CRUD (T-4) ----------------------------

def test_child_cannot_manage_tasks(child_client):
    payload = {
        "task_id": "child_created",
        "subject": "英语",
        "name": "不该被创建",
        "reward": 0.1,
        "weekly_min": 1,
        "sort_weight": 0,
    }
    assert child_client.post("/api/v1/tasks", json=payload).status_code == 403
    assert child_client.put("/api/v1/tasks/en_word", json={"name": "改名"}).status_code == 403
    assert child_client.delete("/api/v1/tasks/en_word").status_code == 403
    # Reading is allowed for both roles.
    assert child_client.get("/api/v1/tasks").status_code == 200
    # Nothing was actually written.
    assert all(t["task_id"] != "child_created" for t in child_client.get("/api/v1/tasks").json())


# --- TaskCreate contract (N-02) ---------------------------------------------

def test_task_create_requires_reward_and_weekly_min(parent_client):
    resp = parent_client.post(
        "/api/v1/tasks",
        json={"task_id": "no_reward", "subject": "英语", "name": "缺字段"},
    )
    assert resp.status_code == 422
    issues = resp.json()["detail"]
    fields = {issue["loc"][-1] for issue in issues if issue.get("loc")}
    assert {"reward", "weekly_min"} <= fields

    # Explicit null is rejected as well, not silently defaulted.
    resp = parent_client.post(
        "/api/v1/tasks",
        json={
            "task_id": "null_reward",
            "subject": "英语",
            "name": "null 字段",
            "reward": None,
            "weekly_min": 3,
        },
    )
    assert resp.status_code == 422


# --- Login rate limit, end-to-end (T-5) -------------------------------------

def test_login_rate_limit_returns_429(client):
    for _ in range(5):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "tayhe", "password": "definitely-wrong"},
        )
        assert resp.status_code == 401

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "tayhe", "password": "definitely-wrong"},
    )
    assert resp.status_code == 429
    assert "过多" in resp.json()["detail"]


# --- Config contract ---------------------------------------------------------

def test_config_exposes_subjects_and_window(client):
    resp = client.get("/api/v1/config")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["subjects"] == config.SUBJECTS
    assert payload["editable_day_window"] == config.EDITABLE_DAY_WINDOW


# --- Seed credentials + single DB_PATH source (Phase 3.6 / A-04) ------------

def test_seed_credentials_read_from_config(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "seeded.db")
    monkeypatch.setattr(config, "INITIAL_PARENT_PASSWORD", "env-driven-secret")

    # Only config.DB_PATH is patched: database.py must read it dynamically.
    database.init_db()

    from backend.main import app

    with TestClient(app) as c:
        ok = c.post("/api/v1/auth/login", json={"username": "tayhe", "password": "env-driven-secret"})
        assert ok.status_code == 200
        bad = c.post("/api/v1/auth/login", json={"username": "tayhe", "password": "parents"})
        assert bad.status_code == 401
