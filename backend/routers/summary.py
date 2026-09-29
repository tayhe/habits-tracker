from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import config, weeks
from ..auth import get_current_user
from ..database import get_db
from ..models import DayRecords, WeekEarn
from ..rules import progress_emoji
from .records import build_day_records, get_records_for_date

router = APIRouter(prefix="/summary", tags=["summary"])


def get_iso_week_range(d: date) -> tuple[date, date]:
    """Return (monday, sunday) of the ISO week containing date d."""
    return weeks.monday_of(d), weeks.sunday_of(d)


@router.get("/daily", response_model=DayRecords)
def daily_summary(d: date = Query(..., alias="date"), user: dict = Depends(get_current_user)):
    records = get_records_for_date(d)
    return build_day_records(d, records)


@router.get("/weekly")
def weekly_summary(week: str = Query(...), user: dict = Depends(get_current_user)):
    """week format: YYYY-WXX, e.g. 2026-W21"""
    monday, sunday = weeks.parse_week_label(week)

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT task_id, name, subject, reward, weekly_min FROM tasks")
        tasks = {row["task_id"]: dict(row) for row in cursor.fetchall()}

        result = {}

        week_start = monday.isoformat()
        week_end = (monday + timedelta(days=7)).isoformat()

        for subject in config.SUBJECTS:
            subject_tasks = [t for t in tasks.values() if t["subject"] == subject]
            task_ids = [t["task_id"] for t in subject_tasks]
            if not task_ids:
                continue

            # Count completions per task this week
            placeholders = ",".join(["?"] * len(task_ids))
            cursor.execute(f"""
                SELECT task_id, COUNT(*) as cnt
                FROM daily_records
                WHERE date >= ? AND date < ? AND task_id IN ({placeholders}) AND completed = 1
                GROUP BY task_id
            """, [week_start, week_end] + task_ids)
            completion_counts = {row["task_id"]: row["cnt"] for row in cursor.fetchall()}

            tasks_met = 0
            total_reward = 0.0
            task_details = []
            for t in subject_tasks:
                cnt = completion_counts.get(t["task_id"], 0)
                qualified = cnt >= t["weekly_min"]
                if qualified:
                    tasks_met += 1
                    total_reward += t["reward"] * cnt
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
                "emoji": progress_emoji(tasks_met, total_tasks),
                "tasks": task_details,
            }

        # Overall
        all_task_ids = list(tasks.keys())
        all_tasks_met = 0
        all_total_tasks = len(all_task_ids)
        if all_task_ids:
            placeholders = ",".join(["?"] * len(all_task_ids))
            cursor.execute(f"""
                SELECT task_id, COUNT(*) as cnt
                FROM daily_records
                WHERE date >= ? AND date < ? AND task_id IN ({placeholders}) AND completed = 1
                GROUP BY task_id
            """, [week_start, week_end] + all_task_ids)
            all_completion_counts = {row["task_id"]: row["cnt"] for row in cursor.fetchall()}

            for t in tasks.values():
                cnt = all_completion_counts.get(t["task_id"], 0)
                if cnt >= t["weekly_min"]:
                    all_tasks_met += 1

    result["总计"] = {
        "week": week,
        "subject": "总计",
        "tasks_met": all_tasks_met,
        "total_tasks": all_total_tasks,
        "rate": round(all_tasks_met / all_total_tasks, 2) if all_total_tasks > 0 else 0,
        "total_reward": round(sum(v["total_reward"] for v in result.values()), 2),
        "emoji": progress_emoji(all_tasks_met, all_total_tasks),
    }

    return result


@router.get("/week-earn", response_model=WeekEarn)
def get_week_earn(
    date: date = Query(..., alias="date"),
    user: dict = Depends(get_current_user)
):
    """Get the cumulative earnings for the week containing the given date."""
    monday, sunday = get_iso_week_range(date)
    week_str = weeks.iso_week_label(monday)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.date, SUM(t.reward) as day_reward
            FROM daily_records r
            JOIN tasks t ON r.task_id = t.task_id
            WHERE r.date >= ? AND r.date <= ? AND r.completed = 1
            GROUP BY r.date
        """, (monday.isoformat(), sunday.isoformat()))
        rows = cursor.fetchall()

    total_earn = sum(row["day_reward"] for row in rows)
    completed_days = len(rows)

    return WeekEarn(
        week=week_str,
        week_start=monday,
        week_end=sunday,
        total_earn=round(total_earn, 2),
        completed_days=completed_days
    )


@router.get("/multi-week")
def multi_week_summary(
    weeks_count: int = Query(8, alias="weeks", ge=1, le=26),
    user: dict = Depends(get_current_user)
):
    """Return summary for the last N weeks for trend comparison."""
    today = date.today()
    current_week_start = today - timedelta(days=today.weekday())

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, name, subject, reward, weekly_min FROM tasks WHERE deleted_at IS NULL")
        tasks = {row["task_id"]: dict(row) for row in cursor.fetchall()}
        all_task_ids = list(tasks.keys())

        results = []
        for i in range(weeks_count):
            offset = i * 7
            week_monday = current_week_start - timedelta(days=offset)
            week_str = weeks.iso_week_label(week_monday)

            week_start_str = week_monday.isoformat()
            week_end_str = (week_monday + timedelta(days=7)).isoformat()

            tasks_met = 0
            total_tasks = len(all_task_ids)
            total_reward = 0.0
            subject_data = {s: {"tasks_met": 0, "total_tasks": 0} for s in config.SUBJECTS}

            if all_task_ids:
                placeholders = ",".join(["?"] * len(all_task_ids))
                cursor.execute(f"""
                    SELECT task_id, COUNT(*) as cnt
                    FROM daily_records
                    WHERE date >= ? AND date < ? AND task_id IN ({placeholders}) AND completed = 1
                    GROUP BY task_id
                """, [week_start_str, week_end_str] + all_task_ids)
                completion_counts = {row["task_id"]: row["cnt"] for row in cursor.fetchall()}

                for t in tasks.values():
                    subject = t["subject"]
                    if subject in subject_data:
                        subject_data[subject]["total_tasks"] += 1
                    cnt = completion_counts.get(t["task_id"], 0)
                    if cnt >= t["weekly_min"]:
                        tasks_met += 1
                        if subject in subject_data:
                            subject_data[subject]["tasks_met"] += 1
                        total_reward += t["reward"] * cnt

            rate = tasks_met / total_tasks if total_tasks > 0 else 0
            results.append({
                "week": week_str,
                "week_start": week_monday.isoformat(),
                "tasks_met": tasks_met,
                "total_tasks": total_tasks,
                "rate": round(rate, 2),
                "total_reward": round(total_reward, 2),
                "emoji": progress_emoji(tasks_met, total_tasks),
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
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO weekly_fulfillment (week, fulfilled, fulfilled_at)
            VALUES (?, ?, ?)
            ON CONFLICT(week) DO UPDATE SET
                fulfilled = excluded.fulfilled,
                fulfilled_at = excluded.fulfilled_at
        """, (week, fulfilled, date.today().isoformat() if fulfilled else None))
        conn.commit()
    return {"message": "Updated"}
