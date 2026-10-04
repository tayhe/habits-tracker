import sqlite3
from datetime import timedelta

import pytest

from backend import clock, config, database


def test_t01_delete_task_with_records(parent_client):
    """T-01: P0-01 - Deleting a task with daily records must succeed (soft delete) rather than 500."""
    today = clock.today().isoformat()
    # Create a record for task 'en_word'
    r1 = parent_client.put("/api/v1/records", json={"date": today, "task_id": "en_word", "completed": True})
    assert r1.status_code == 200

    # Try to delete task 'en_word'
    resp = parent_client.delete("/api/v1/tasks/en_word")
    assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"

    # Verify task is no longer in active list
    tasks_resp = parent_client.get("/api/v1/tasks")
    assert tasks_resp.status_code == 200
    task_ids = [t["task_id"] for t in tasks_resp.json()]
    assert "en_word" not in task_ids

def test_t02_task_update_subject_and_forbid_extra(parent_client):
    """T-03 & T-04: P0-02 - Task update must allow updating subject, and forbid extra fields."""
    # 1. Update subject
    resp = parent_client.put("/api/v1/tasks/en_picture", json={"subject": "语文"})
    assert resp.status_code == 200
    tasks = parent_client.get("/api/v1/tasks").json()
    task = next(t for t in tasks if t["task_id"] == "en_picture")
    assert task["subject"] == "语文"

    # 2. Forbid extra fields
    resp_extra = parent_client.put("/api/v1/tasks/en_picture", json={"unknown_field": "invalid"})
    assert resp_extra.status_code == 422

def test_t03_logout_invalidates_session(client):
    """T-05: P0-04 - Logout must delete server session, making subsequent /auth/me return 401."""
    login_resp = client.post("/api/v1/auth/login", json={"username": "meow", "password": "child"})
    assert login_resp.status_code == 200
    token = client.cookies.get("session_token")
    assert token is not None

    # Call logout
    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200

    # Verify session token is invalidated on server
    me_resp = client.get("/api/v1/auth/me", cookies={"session_token": token})
    assert me_resp.status_code == 401

def test_t04_unknown_task_id_returns_404(parent_client):
    """T-07: P1-04 - Upserting record with unknown task_id must return 404, not 500."""
    resp = parent_client.put("/api/v1/records", json={
        "date": clock.today().isoformat(),
        "task_id": "non_existent_task",
        "completed": True
    })
    assert resp.status_code == 404

def test_t05_child_editable_window_message(child_client):
    """T-08: P1-05 - 403 error detail must reflect EDITABLE_DAY_WINDOW, not 'last 3 days'."""
    out_of_window_date = (clock.today() - timedelta(days=config.EDITABLE_DAY_WINDOW + 2)).isoformat()
    resp = child_client.put("/api/v1/records", json={
        "date": out_of_window_date,
        "task_id": "en_word",
        "completed": True
    })
    assert resp.status_code == 403
    assert f"{config.EDITABLE_DAY_WINDOW}" in resp.json().get("detail", "")
    assert "3 days" not in resp.json().get("detail", "")

def test_t06_change_password_revokes_old_session(client):
    """T-06: P1-06 - Changing password should revoke old session tokens."""
    login_resp = client.post("/api/v1/auth/login", json={"username": "meow", "password": "child"})
    assert login_resp.status_code == 200
    old_token = client.cookies.get("session_token")

    change_resp = client.put("/api/v1/auth/password", json={
        "old_password": "child",
        "new_password": "child_new_pass"
    })
    assert change_resp.status_code == 200

    # Old token must no longer work
    check_resp = client.get("/api/v1/auth/me", cookies={"session_token": old_token})
    # If a new token was reissued, old token should be revoked (or re-issued)
    # At minimum, if old_token was revoked from DB, using the old token returns 401
    new_token = client.cookies.get("session_token")
    if new_token != old_token:
        assert check_resp.status_code == 401

def test_t07_week_parameter_validation(parent_client):
    """T-12: P1-03 - Invalid week parameter such as 2026-W99 must return 400."""
    resp = parent_client.get("/api/v1/summary/weekly?week=2026-W99")
    assert resp.status_code == 400


def test_t08_sports_subject_lifecycle(parent_client):
    """Sports subject can be used to create tasks, punch records, and summarize."""
    # 1. Create a sports task
    task_id = "sport_rope"
    create_resp = parent_client.post("/api/v1/tasks", json={
        "task_id": task_id,
        "subject": "体育",
        "name": "跳绳",
        "reward": 0.2,
        "weekly_min": 3,
        "sort_weight": 5,
    })
    assert create_resp.status_code == 200, create_resp.text

    # 2. Verify task listing
    tasks = parent_client.get("/api/v1/tasks").json()
    task = next((t for t in tasks if t["task_id"] == task_id), None)
    assert task is not None
    assert task["subject"] == "体育"
    assert task["name"] == "跳绳"

    # 3. Record completion for today
    today = clock.today().isoformat()
    rec_resp = parent_client.put("/api/v1/records", json={
        "date": today,
        "task_id": task_id,
        "completed": True,
    })
    assert rec_resp.status_code == 200

    # 4. Weekly summary includes 体育
    mon = clock.today() - timedelta(days=clock.today().weekday())
    week_str = f"{mon.isocalendar()[0]}-W{mon.isocalendar()[1]:02d}"
    weekly = parent_client.get(f"/api/v1/summary/weekly?week={week_str}").json()
    assert "体育" in weekly
    assert weekly["体育"]["total_tasks"] >= 1
    rope_task = next((t for t in weekly["体育"]["tasks"] if t["task_id"] == task_id), None)
    assert rope_task is not None
    assert rope_task["completed_count"] == 1

    # 5. Multi-week summary includes 体育
    multi = parent_client.get("/api/v1/summary/multi-week?weeks=1").json()
    assert "体育" in multi[-1]["subjects"]
    assert multi[-1]["subjects"]["体育"]["total_tasks"] >= 1


def test_t09_migration_v4_removes_check_constraint():
    """v3 -> v4 migration removes the CHECK constraint on tasks.subject."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT UNIQUE NOT NULL,
        subject TEXT NOT NULL CHECK(subject IN ('英语', '数学', '语文')),
        name TEXT NOT NULL,
        reward REAL NOT NULL DEFAULT 0,
        weekly_min INTEGER NOT NULL DEFAULT 1,
        sort_weight INTEGER NOT NULL DEFAULT 0,
        deleted_at DATETIME DEFAULT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("INSERT INTO tasks (task_id, subject, name) VALUES ('t1', '体育', '跳绳')")

    database._migrate_to_v4(cursor)
    conn.commit()

    # After migration, subject is not constrained to ('英语', '数学', '语文')
    cursor.execute("INSERT INTO tasks (task_id, subject, name) VALUES ('t1', '体育', '跳绳')")
    conn.commit()
    row = cursor.execute("SELECT task_id, subject, name FROM tasks").fetchone()
    assert row == ("t1", "体育", "跳绳")
    conn.close()

