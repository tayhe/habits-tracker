from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List
from datetime import date, datetime, timedelta
from models import RecordUpdate, RecordOut, DayRecords, WeekRecords, TaskProgress
from database import get_db
from auth import get_current_user
import config

router = APIRouter(prefix="/records", tags=["records"])


def progress_emoji(completed_count: int, total_count: int) -> str:
    if total_count == 0:
        return "😿"
    rate = completed_count / total_count
    if rate >= 1.0:
        return "😺🎉"
    elif rate >= 0.75:
        return "😺"
    elif rate >= 0.5:
        return "😸"
    elif rate >= 0.25:
        return "😼"
    elif rate > 0:
        return "😾"
    else:
        return "😿"


def get_records_for_date(d: date) -> List[RecordOut]:
    """Get all tasks for a date, with completed=false for missing records."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, name, subject, reward FROM tasks ORDER BY sort_weight DESC")
        task_rows = cursor.fetchall()
        cursor.execute("SELECT task_id, completed FROM daily_records WHERE date = ?", (d.isoformat(),))
        record_map = {row["task_id"]: bool(row["completed"]) for row in cursor.fetchall()}
    return [
        RecordOut(
            date=d.isoformat(),
            task_id=t["task_id"],
            task_name=t["name"],
            subject=t["subject"],
            reward=t["reward"],
            completed=record_map.get(t["task_id"], False)
        )
        for t in task_rows
    ]


def build_day_records(d: date, records: List[RecordOut]) -> DayRecords:
    """Build a DayRecords response from a list of records."""
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


@router.get("", response_model=DayRecords)
def get_day_records(date: date = Query(...), user: dict = Depends(get_current_user)):
    records = get_records_for_date(date)
    return build_day_records(date, records)


@router.get("/range", response_model=List[DayRecords])
def get_range_records(
    start: date = Query(...),
    end: date = Query(...),
    user: dict = Depends(get_current_user)
):
    result = []
    d = start
    while d <= end:
        records = get_records_for_date(d)
        result.append(build_day_records(d, records))
        d += timedelta(days=1)
    return result


@router.get("/week", response_model=WeekRecords)
def get_week_records(
    date: date = Query(..., description="Any date in the target week"),
    user: dict = Depends(get_current_user)
):
    """Get all 7 days records for the week containing the given date."""
    monday = date - timedelta(days=date.weekday())
    sunday = monday + timedelta(days=6)
    week_start_str = monday.isoformat()
    week_end_str = (monday + timedelta(days=7)).isoformat()

    days = []
    week_total_earn = 0.0
    week_completed_days = 0

    for i in range(7):
        d = monday + timedelta(days=i)
        records = get_records_for_date(d)
        day_records = build_day_records(d, records)
        week_total_earn += day_records.total_reward
        if day_records.completed_count >= day_records.total_count / 2:
            week_completed_days += 1
        days.append(day_records)

    # Per-task weekly progress
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, name, subject, reward, weekly_min FROM tasks ORDER BY sort_weight DESC")
        all_tasks = cursor.fetchall()
        task_ids = [t["task_id"] for t in all_tasks]
        if task_ids:
            placeholders = ",".join("?" * len(task_ids))
            cursor.execute(f"""
                SELECT task_id, COUNT(*) as cnt
                FROM daily_records
                WHERE completed = 1 AND date >= ? AND date < ?
                AND task_id IN ({placeholders})
                GROUP BY task_id
            """, [week_start_str, week_end_str] + task_ids)
            counts = {row["task_id"]: row["cnt"] for row in cursor.fetchall()}
        else:
            counts = {}

    task_progress = []
    for t in all_tasks:
        cnt = counts.get(t["task_id"], 0)
        task_progress.append(TaskProgress(
            task_id=t["task_id"],
            name=t["name"],
            subject=t["subject"],
            reward=t["reward"],
            weekly_min=t["weekly_min"],
            completed_count=cnt,
            qualified=cnt >= t["weekly_min"]
        ))

    return WeekRecords(
        week_start=monday,
        week_end=sunday,
        days=days,
        week_total_earn=round(week_total_earn, 2),
        week_completed_days=week_completed_days,
        task_progress=task_progress
    )


@router.put("")
def upsert_record(update: RecordUpdate, user: dict = Depends(get_current_user)):
    """Update a single record. Child users can only update records within the last 3 days."""
    if user["role"] == "child":
        today = date.today()
        three_days_ago = today - timedelta(days=config.EDITABLE_DAY_WINDOW - 1)
        if update.date < three_days_ago or update.date > today:
            raise HTTPException(
                status_code=403,
                detail="Child users can only update records from the last 3 days"
            )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO daily_records (date, task_id, completed, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, task_id) DO UPDATE SET
                completed = excluded.completed,
                updated_at = excluded.updated_at
        """, (update.date.isoformat(), update.task_id, update.completed, datetime.now().isoformat()))
        conn.commit()
    return {"message": "Record updated"}


@router.put("/batch")
def upsert_records_batch(
    updates: List[RecordUpdate],
    user: dict = Depends(get_current_user)
):
    """Batch update records. Child users can only update records within the last 3 days."""
    if user["role"] == "child":
        today = date.today()
        three_days_ago = today - timedelta(days=config.EDITABLE_DAY_WINDOW - 1)
        for update in updates:
            if update.date < three_days_ago or update.date > today:
                raise HTTPException(
                    status_code=403,
                    detail="Child users can only update records from the last 3 days"
                )

    with get_db() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        for update in updates:
            cursor.execute("""
                INSERT INTO daily_records (date, task_id, completed, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date, task_id) DO UPDATE SET
                    completed = excluded.completed,
                    updated_at = excluded.updated_at
            """, (update.date.isoformat(), update.task_id, update.completed, now))
        conn.commit()
    return {"message": f"Updated {len(updates)} records"}
