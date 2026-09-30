from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from backend import clock
from backend.routers.auth_router import BoundedRateLimiter


def test_clock_mock_and_shanghai_timezone(child_client):
    """P1-02: Ensure 00:30 Beijing time (16:30 UTC previous day) allows child check-in for 'today'."""
    # Simulate 2026-10-01 00:30:00 in Asia/Shanghai
    cst_time = datetime(2026, 10, 1, 0, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    clock.set_mock_time(cst_time)
    try:
        assert clock.today() == date(2026, 10, 1)

        # Child check-in for 'today' (2026-10-01) must succeed (200), not 403
        resp = child_client.put("/api/v1/records", json={
            "date": "2026-10-01",
            "task_id": "en_word",
            "completed": True,
        })
        assert resp.status_code == 200
    finally:
        clock.set_mock_time(None)


def test_parent_future_date_punch_rejected(parent_client):
    """P2-06: Parent punching cards on future dates must be rejected with 400."""
    tomorrow = (clock.today() + timedelta(days=1)).isoformat()
    parent_resp = parent_client.put("/api/v1/records", json={
        "date": tomorrow,
        "task_id": "en_word",
        "completed": True,
    })
    assert parent_resp.status_code == 400
    assert "不能超过今天" in parent_resp.json()["detail"]


def test_child_future_date_punch_rejected(child_client):
    """P2-06: Child punching cards on future dates must be rejected with 403."""
    tomorrow = (clock.today() + timedelta(days=1)).isoformat()
    child_resp = child_client.put("/api/v1/records", json={
        "date": tomorrow,
        "task_id": "en_word",
        "completed": True,
    })
    assert child_resp.status_code == 403


def test_task_update_rejects_nulls_and_invalid_values(parent_client):
    """P2-07 & A-01: TaskUpdate must reject explicit nulls, negative rewards, and unknown subjects."""
    # 1. Explicit null reward must be rejected (422) instead of fake success 200
    resp_null = parent_client.put("/api/v1/tasks/en_word", json={"name": "新单词", "reward": None})
    assert resp_null.status_code == 422

    # 2. Negative reward rejected (422)
    resp_neg = parent_client.put("/api/v1/tasks/en_word", json={"reward": -0.5})
    assert resp_neg.status_code == 422

    # 3. Invalid subject rejected (422)
    resp_subj = parent_client.put("/api/v1/tasks/en_word", json={"subject": "物理"})
    assert resp_subj.status_code == 422

    # 4. Valid update succeeds
    resp_ok = parent_client.put("/api/v1/tasks/en_word", json={"reward": 0.2})
    assert resp_ok.status_code == 200


def test_rate_limiter_bounded_memory_and_limits():
    """P2-05: Rate limiter must enforce budgets and cap in-memory storage capacity."""
    limiter = BoundedRateLimiter(max_keys=100, window_seconds=60, max_ip_attempts=10, max_pair_attempts=3)

    # 3 attempts for same pair succeed
    for _ in range(3):
        limiter.check("127.0.0.1", "testuser")
        limiter.record_failure("127.0.0.1", "testuser")

    # 4th attempt rejected
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        limiter.check("127.0.0.1", "testuser")
    assert exc.value.status_code == 429

    # Adding 300 different keys does not balloon memory beyond max_keys
    for i in range(300):
        limiter.record_failure(f"10.0.0.{i % 250}", f"user{i}")

    limiter.check("192.168.1.1", "newuser")
    assert len(limiter._attempts) <= 100
