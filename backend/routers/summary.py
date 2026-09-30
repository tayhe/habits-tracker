from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import clock, config, repo, rules, weeks
from ..auth import get_current_user
from ..database import get_db
from ..models import DayRecords
from .records import build_day_records, get_records_for_date

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("/daily", response_model=DayRecords)
def daily_summary(d: date = Query(..., alias="date"), user: dict = Depends(get_current_user)):
    records = get_records_for_date(d)
    return build_day_records(d, records)


@router.get("/weekly")
def weekly_summary(week: str = Query(...), user: dict = Depends(get_current_user)):
    """week format: YYYY-WXX, e.g. 2026-W21"""
    monday, _ = weeks.parse_week_label(week)
    week_start = monday.isoformat()
    week_end = (monday + timedelta(days=7)).isoformat()

    with get_db() as conn:
        task_rows = repo.get_active_tasks(conn)
        tasks = {t["task_id"]: dict(t) for t in task_rows}
        all_task_ids = list(tasks.keys())
        completion_counts = repo.get_completion_counts(conn, week_start, week_end, all_task_ids)

    result = {}

    for subject in config.SUBJECTS:
        subject_tasks = [t for t in tasks.values() if t["subject"] == subject]
        if not subject_tasks:
            continue

        tasks_met = 0
        total_reward = 0.0
        task_details = []
        for t in subject_tasks:
            cnt = completion_counts.get(t["task_id"], 0)
            qualified = cnt >= t["weekly_min"]
            if qualified:
                tasks_met += 1
            total_reward += rules.calculate_reward(t["reward"], t["weekly_min"], cnt)
            task_details.append({
                "task_id": t["task_id"],
                "name": t["name"],
                "weekly_min": t["weekly_min"],
                "completed_count": cnt,
                "qualified": qualified,
            })

        total_tasks = len(subject_tasks)
        rate = tasks_met / total_tasks if total_tasks > 0 else 0

        result[subject] = {
            "week": week,
            "subject": subject,
            "tasks_met": tasks_met,
            "total_tasks": total_tasks,
            "rate": round(rate, 2),
            "total_reward": round(total_reward, 2),
            "emoji": rules.progress_emoji(tasks_met, total_tasks),
            "tasks": task_details,
        }

    all_tasks_met = sum(
        1 for t in tasks.values()
        if completion_counts.get(t["task_id"], 0) >= t["weekly_min"]
    )
    all_total_tasks = len(all_task_ids)

    result["总计"] = {
        "week": week,
        "subject": "总计",
        "tasks_met": all_tasks_met,
        "total_tasks": all_total_tasks,
        "rate": round(all_tasks_met / all_total_tasks, 2) if all_total_tasks > 0 else 0,
        "total_reward": round(sum(v["total_reward"] for v in result.values()), 2),
        "emoji": rules.progress_emoji(all_tasks_met, all_total_tasks),
    }

    return result


@router.get("/multi-week")
def multi_week_summary(
    weeks_count: int = Query(8, alias="weeks", ge=1, le=26),
    user: dict = Depends(get_current_user),
):
    """Return summary for the last N weeks for trend comparison."""
    today = clock.today()
    current_week_start = today - timedelta(days=today.weekday())

    with get_db() as conn:
        task_rows = repo.get_active_tasks(conn)
        tasks = {t["task_id"]: dict(t) for t in task_rows}
        all_task_ids = list(tasks.keys())

        # One query covers every week in the span instead of one query per week.
        span_start = current_week_start - timedelta(days=7 * (weeks_count - 1))
        span_end = current_week_start + timedelta(days=7)  # exclusive
        counts_by_week = repo.get_completion_counts_by_week(
            conn, span_start.isoformat(), span_end.isoformat(), all_task_ids
        )

        results = []
        for i in range(weeks_count):
            offset = i * 7
            week_monday = current_week_start - timedelta(days=offset)
            week_str = weeks.iso_week_label(week_monday)

            tasks_met = 0
            total_tasks = len(all_task_ids)
            total_reward = 0.0
            subject_data = {s: {"tasks_met": 0, "total_tasks": 0} for s in config.SUBJECTS}

            for t in tasks.values():
                subject = t["subject"]
                if subject in subject_data:
                    subject_data[subject]["total_tasks"] += 1
                cnt = counts_by_week.get((week_str, t["task_id"]), 0)
                if cnt >= t["weekly_min"]:
                    tasks_met += 1
                    if subject in subject_data:
                        subject_data[subject]["tasks_met"] += 1
                total_reward += rules.calculate_reward(t["reward"], t["weekly_min"], cnt)

            rate = tasks_met / total_tasks if total_tasks > 0 else 0
            results.append({
                "week": week_str,
                "week_start": week_monday.isoformat(),
                "tasks_met": tasks_met,
                "total_tasks": total_tasks,
                "rate": round(rate, 2),
                "total_reward": round(total_reward, 2),
                "emoji": rules.progress_emoji(tasks_met, total_tasks),
                "subjects": {
                    s: {
                        "tasks_met": subject_data[s]["tasks_met"],
                        "total_tasks": subject_data[s]["total_tasks"],
                    } for s in config.SUBJECTS
                },
            })

    results.reverse()  # oldest first
    return results


@router.get("/fulfillment")
def get_fulfillment(weeks: List[str] = Query(...), user: dict = Depends(get_current_user)):
    """Get fulfillment status for multiple weeks."""
    if len(weeks) > 60:
        raise HTTPException(status_code=400, detail="查询周数不能超过60周")
    with get_db() as conn:
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(weeks))
        cursor.execute(f"""
            SELECT week, fulfilled FROM weekly_fulfillment
            WHERE week IN ({placeholders})
        """, weeks)
        rows = {row["week"]: bool(row["fulfilled"]) for row in cursor.fetchall()}
    return rows


@router.put("/fulfillment")
def update_fulfillment(week: str, fulfilled: bool, user: dict = Depends(get_current_user)):
    """Update fulfillment status for a week. Only parent can update."""
    if user["role"] != "parent":
        raise HTTPException(status_code=403, detail="Only parent can update fulfillment")
    weeks.parse_week_label(week)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO weekly_fulfillment (week, fulfilled, fulfilled_at)
            VALUES (?, ?, ?)
            ON CONFLICT(week) DO UPDATE SET
                fulfilled = excluded.fulfilled,
                fulfilled_at = excluded.fulfilled_at
        """, (week, fulfilled, clock.today().isoformat() if fulfilled else None))
        conn.commit()
    return {"message": "Updated"}
