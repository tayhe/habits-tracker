from datetime import timedelta

from backend import clock


def test_archived_task_consistent_across_endpoints(parent_client):
    """P1-01: Soft-deleted tasks must be consistently excluded from weekly, multi-week, and records/week."""
    mon = clock.today() - timedelta(days=clock.today().weekday())
    week_str = f"{mon.isocalendar()[0]}-W{mon.isocalendar()[1]:02d}"

    # Record completion for en_recite
    r1 = parent_client.put("/api/v1/records", json={"date": mon.isoformat(), "task_id": "en_recite", "completed": True})
    assert r1.status_code == 200

    # Before archiving
    weekly_before = parent_client.get(f"/api/v1/summary/weekly?week={week_str}").json()["英语"]
    multi_before = parent_client.get("/api/v1/summary/multi-week?weeks=1").json()[-1]["subjects"]["英语"]
    records_before = parent_client.get(f"/api/v1/records/week?date={mon.isoformat()}").json()["task_progress"]
    en_records_before = [tp for tp in records_before if tp["subject"] == "英语"]

    assert weekly_before["total_tasks"] == multi_before["total_tasks"] == len(en_records_before)

    # Soft delete / archive en_recite
    del_resp = parent_client.delete("/api/v1/tasks/en_recite")
    assert del_resp.status_code == 200

    # After archiving
    weekly_after = parent_client.get(f"/api/v1/summary/weekly?week={week_str}").json()["英语"]
    multi_after = parent_client.get("/api/v1/summary/multi-week?weeks=1").json()[-1]["subjects"]["英语"]
    records_after = parent_client.get(f"/api/v1/records/week?date={mon.isoformat()}").json()["task_progress"]
    en_records_after = [tp for tp in records_after if tp["subject"] == "英语"]

    # All three must agree: total_tasks decremented by 1, and en_recite excluded
    assert weekly_after["total_tasks"] == multi_after["total_tasks"] == len(en_records_after)
    assert weekly_after["total_tasks"] == weekly_before["total_tasks"] - 1
    assert weekly_after["tasks_met"] == multi_after["tasks_met"]
    assert weekly_after["total_reward"] == 0.0


def test_empty_day_completed_days_zero(parent_client):
    """P2-03: When there are no tasks, week_completed_days must be 0, not 7."""
    mon = clock.today() - timedelta(days=clock.today().weekday())

    # Archive all tasks
    tasks = parent_client.get("/api/v1/tasks").json()
    for t in tasks:
        parent_client.delete(f"/api/v1/tasks/{t['task_id']}")

    res = parent_client.get(f"/api/v1/records/week?date={mon.isoformat()}").json()
    assert res["week_completed_days"] == 0


def test_fulfillment_week_validation(parent_client):
    """P2-04: PUT /summary/fulfillment must validate week label format, and GET must limit list size."""
    # Invalid week string rejected with 400
    res_bad = parent_client.put("/api/v1/summary/fulfillment?week=garbage&fulfilled=true")
    assert res_bad.status_code == 400

    # Valid week format accepted
    mon = clock.today() - timedelta(days=clock.today().weekday())
    valid_week = f"{mon.isocalendar()[0]}-W{mon.isocalendar()[1]:02d}"
    res_ok = parent_client.put(f"/api/v1/summary/fulfillment?week={valid_week}&fulfilled=true")
    assert res_ok.status_code == 200

    # GET with > 60 items rejected
    too_many = [f"2026-W{i:02d}" for i in range(1, 65)]
    query = "&".join([f"weeks={w}" for w in too_many])
    res_limit = parent_client.get(f"/api/v1/summary/fulfillment?{query}")
    assert res_limit.status_code == 400


def test_child_cannot_update_fulfillment(child_client):
    """Child user must not be able to update weekly fulfillment."""
    mon = clock.today() - timedelta(days=clock.today().weekday())
    valid_week = f"{mon.isocalendar()[0]}-W{mon.isocalendar()[1]:02d}"
    res = child_client.put(f"/api/v1/summary/fulfillment?week={valid_week}&fulfilled=true")
    assert res.status_code == 403
