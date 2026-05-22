from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import date, timedelta
from models import DayRecords, WeekEarn
from database import get_db
from routers.records import get_records_for_date, build_day_records, progress_emoji
from auth import get_current_user
import config

router = APIRouter(prefix="/summary", tags=["summary"])


def get_iso_week_range(d: date) -> tuple[date, date]:
    """Return (monday, sunday) of the ISO week containing date d."""
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


@router.get("/daily", response_model=DayRecords)
def daily_summary(d: date = Query(..., alias="date"), user: dict = Depends(get_current_user)):
    records = get_records_for_date(d)
    return build_day_records(d, records)


@router.get("/weekly")
def weekly_summary(week: str = Query(...), user: dict = Depends(get_current_user)):
    """week format: YYYY-WXX, e.g. 2026-W21"""
    try:
        year, week_part = week.split("-W")
        year = int(year)
        week_num = int(week_part)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid week format, use YYYY-WXX")

    # Get Monday of that ISO week
    jan4 = date(year, 1, 4)
    monday = jan4 - timedelta(days=jan4.weekday()) + timedelta(weeks=week_num - 1)
    sunday = monday + timedelta(days=6)

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT task_id, name, subject, reward, weekly_min FROM tasks")
        tasks = {row["task_id"]: dict(row) for row in cursor.fetchall()}

        result = {}

        for subject in config.SUBJECTS:
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

            total_reward = sum(t["reward"] * min(completed_days, t["weekly_min"])
                               for t in subject_tasks)
            rate = completed_days / 7

            result[subject] = {
                "week": week,
                "subject": subject,
                "completed_days": completed_days,
                "total_days": 7,
                "rate": round(rate, 2),
                "total_reward": round(total_reward, 2),
                "emoji": progress_emoji(completed_days, 7),
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

    return result


@router.get("/week-earn", response_model=WeekEarn)
def get_week_earn(
    date: date = Query(..., alias="date"),
    user: dict = Depends(get_current_user)
):
    """Get the cumulative earnings for the week containing the given date."""
    monday, sunday = get_iso_week_range(date)
    week_str = f"{date.year}-W{date.isocalendar()[1]:02d}"

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
