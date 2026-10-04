"""Phase 5 quick wins: /health DB probe and multi-week query batching."""

import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from backend import clock, database

# --- /health readiness probe -------------------------------------------------

def test_health_reports_database_state(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["db"]["journal_mode"] == "wal"
    assert payload["db"]["schema_version"] >= 3


def test_health_returns_503_when_database_unavailable(client, monkeypatch):
    def broken_connection():
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(database, "get_connection", broken_connection)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert "数据库不可用" in resp.json()["detail"]


# --- multi-week batching -----------------------------------------------------

def test_multi_week_matches_weekly_endpoint(parent_client):
    """The batched span query must produce the same numbers as /summary/weekly."""
    clock.set_mock_time(datetime(2026, 9, 30, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    this_monday = date(2026, 9, 28)      # 2026-W40
    last_monday = date(2026, 9, 21)      # 2026-W39

    for i in range(3):                   # en_recite (min 1/week): qualifies in W40
        parent_client.put("/api/v1/records", json={
            "date": (this_monday + timedelta(days=i)).isoformat(),
            "task_id": "en_recite",
            "completed": True,
        })
    for i in range(6):                   # math_extra: 6 completions last week (min 5)
        parent_client.put("/api/v1/records", json={
            "date": (last_monday + timedelta(days=i)).isoformat(),
            "task_id": "math_extra",
            "completed": True,
        })

    multi = {w["week"]: w for w in parent_client.get("/api/v1/summary/multi-week?weeks=2").json()}
    assert set(multi) == {"2026-W40", "2026-W39"}
    # Guard against a vacuous comparison: both weeks must carry real earnings.
    assert multi["2026-W40"]["total_reward"] > 0
    assert multi["2026-W39"]["total_reward"] > 0

    for label in ("2026-W40", "2026-W39"):
        weekly = parent_client.get(f"/api/v1/summary/weekly?week={label}").json()
        assert multi[label]["total_reward"] == weekly["总计"]["total_reward"], label
        assert multi[label]["tasks_met"] == weekly["总计"]["tasks_met"], label
        assert multi[label]["total_tasks"] == weekly["总计"]["total_tasks"], label
        for subject in ("英语", "数学", "语文"):
            assert multi[label]["subjects"][subject]["tasks_met"] == weekly[subject]["tasks_met"], label
            assert multi[label]["subjects"][subject]["total_tasks"] == weekly[subject]["total_tasks"], label


def test_multi_week_issues_single_records_query(parent_client, monkeypatch):
    """Regression guard: 8 weeks must cost one daily_records query, not eight."""
    real_get_connection = database.get_connection
    traces: list[str] = []

    def traced_connection():
        conn = real_get_connection()
        conn.set_trace_callback(traces.append)
        return conn

    monkeypatch.setattr(database, "get_connection", traced_connection)

    resp = parent_client.get("/api/v1/summary/multi-week?weeks=8")
    assert resp.status_code == 200
    assert len(resp.json()) == 8

    queries = [
        t.strip() for t in traces
        if t.strip().upper().startswith("SELECT") and "FROM DAILY_RECORDS" in t.upper()
    ]
    assert len(queries) == 1, queries
