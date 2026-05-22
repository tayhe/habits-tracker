from fastapi import APIRouter, Query
from typing import List
from datetime import date, timedelta
from models import DayRecords
from database import get_connection
from routers.records import get_tasks_for_date, progress_emoji

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("/daily", response_model=DayRecords)
def daily_summary(d: date = Query(..., alias="date")):
    records = get_tasks_for_date(d)
    total = len(records)
    completed = sum(1 for r in records if r.completed)
    total_reward = sum(r.reward for r in records if r.completed)
    return DayRecords(
        date=d,
        records=records,
        total_reward=round(total_reward, 2),
        completed_count=completed,
        total_count=total,
        emoji=progress_emoji(completed, total)
    )


@router.get("/weekly")
def weekly_summary(week: str = Query(...)):
    """
    week format: YYYY-WXX, e.g. 2026-W21
    Returns summary by subject for the given ISO week.
    """
    # Parse week string
    try:
        year, week_part = week.split("-W")
        year = int(year)
        week_num = int(week_part)
    except ValueError:
        return {"error": "Invalid week format, use YYYY-WXX"}

    # Get Monday of that week
    jan4 = date(year, 1, 4)
    monday = jan4 + timedelta(weeks=week_num - 1)
    # Adjust to the Monday of the week containing Jan 4 (ISO week start)
    monday = monday - timedelta(days=monday.weekday())

    conn = get_connection()
    cursor = conn.cursor()

    # Get all tasks grouped by subject
    cursor.execute("SELECT task_id, name, subject, reward, weekly_min FROM tasks")
    tasks = {row["task_id"]: dict(row) for row in cursor.fetchall()}

    subjects = ["英语", "数学", "语文"]
    result = {}

    for subject in subjects:
        subject_tasks = [t for t in tasks.values() if t["subject"] == subject]
        task_ids = [t["task_id"] for t in subject_tasks]
        if not task_ids:
            continue

        placeholders = ",".join(["?"] * len(task_ids))
        cursor.execute(f"""
            SELECT date, COUNT(*) as completed_count
            FROM daily_records
            WHERE date >= ? AND date < ? AND task_id IN ({placeholders}) AND completed = 1
            GROUP BY date
        """, [monday.isoformat(), (monday + timedelta(days=7)).isoformat()] + task_ids)
        completed_days = len(cursor.fetchall())

        cursor.execute(f"""
            SELECT COUNT(DISTINCT date) as active_days
            FROM daily_records
            WHERE date >= ? AND date < ? AND task_id IN ({placeholders}) AND completed = 1
        """, [monday.isoformat(), (monday + timedelta(days=7)).isoformat()] + task_ids)

        # Calculate expected completed days per task
        total_expected = sum(t["weekly_min"] for t in subject_tasks)
        total_reward = sum(t["reward"] * min(completed_days, t["weekly_min"])
                           for t in subject_tasks)

        rate = completed_days / 7
        emoji = progress_emoji(completed_days, 7)

        result[subject] = {
            "week": week,
            "subject": subject,
            "completed_days": completed_days,
            "total_days": 7,
            "rate": round(rate, 2),
            "total_reward": round(total_reward, 2),
            "emoji": emoji,
            "task_count": len(subject_tasks)
        }

    # Overall
    all_task_ids = list(tasks.keys())
    if all_task_ids:
        placeholders = ",".join(["?"] * len(all_task_ids))
        cursor.execute(f"""
            SELECT date, COUNT(*) as completed_count
            FROM daily_records
            WHERE date >= ? AND date < ? AND task_id IN ({placeholders}) AND completed = 1
            GROUP BY date
        """, [monday.isoformat(), (monday + timedelta(days=7)).isoformat()] + all_task_ids)
        completed_days = len(cursor.fetchall())
    else:
        completed_days = 0

    result["总计"] = {
        "week": week,
        "subject": "总计",
        "completed_days": completed_days,
        "total_days": 7,
        "rate": round(completed_days / 7, 2),
        "total_reward": round(sum(v["total_reward"] for v in result.values()), 2),
        "emoji": progress_emoji(completed_days, 7),
        "task_count": len(all_task_ids)
    }

    conn.close()
    return result