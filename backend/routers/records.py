from fastapi import APIRouter, HTTPException, Query
from typing import List
from datetime import date, datetime, timedelta
from models import RecordUpdate, RecordOut, DayRecords
from database import get_connection
from dateutil.parser import parse as parse_date
from dateutil.rrule import MO

router = APIRouter(prefix="/records", tags=["records"])


def progress_emoji(completed_count: int, total_count: int) -> str:
    if total_count == 0:
        return "😭"
    rate = completed_count / total_count
    if rate >= 1.0:
        return "🐟🐡"
    elif rate >= 0.5:
        return "🐟"
    else:
        return "😭"


def get_records_for_date(d: date) -> List[RecordOut]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.date, r.task_id, t.name, t.subject, t.reward, r.completed
        FROM daily_records r
        JOIN tasks t ON r.task_id = t.task_id
        WHERE r.date = ?
        ORDER BY t.sort_weight DESC
    """, (d.isoformat(),))
    rows = cursor.fetchall()
    conn.close()
    return [RecordOut(date=row["date"], task_id=row["task_id"],
                      task_name=row["name"], subject=row["subject"],
                      reward=row["reward"], completed=bool(row["completed"]))
            for row in rows]


def get_tasks_for_date(d: date) -> List[RecordOut]:
    """Get all tasks for a date, with completed=false for missing records."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT task_id, name, subject, reward FROM tasks ORDER BY sort_weight DESC")
    task_rows = cursor.fetchall()
    cursor.execute("SELECT task_id, completed FROM daily_records WHERE date = ?", (d.isoformat(),))
    record_map = {row["task_id"]: bool(row["completed"]) for row in cursor.fetchall()}
    conn.close()
    records = []
    for t in task_rows:
        records.append(RecordOut(
            date=d.isoformat(),
            task_id=t["task_id"],
            task_name=t["name"],
            subject=t["subject"],
            reward=t["reward"],
            completed=record_map.get(t["task_id"], False)
        ))
    return records


@router.get("", response_model=DayRecords)
def get_day_records(date: date = Query(...)):
    records = get_tasks_for_date(date)
    total = len(records)
    completed = sum(1 for r in records if r.completed)
    total_reward = sum(r.reward for r in records if r.completed)
    return DayRecords(
        date=date,
        records=records,
        total_reward=round(total_reward, 2),
        completed_count=completed,
        total_count=total,
        emoji=progress_emoji(completed, total)
    )


@router.get("/range", response_model=List[DayRecords])
def get_range_records(
    start: date = Query(...),
    end: date = Query(...)
):
    from datetime import timedelta
    result = []
    d = start
    while d <= end:
        records = get_tasks_for_date(d)
        total = len(records)
        completed = sum(1 for r in records if r.completed)
        total_reward = sum(r.reward for r in records if r.completed)
        result.append(DayRecords(
            date=d,
            records=records,
            total_reward=round(total_reward, 2),
            completed_count=completed,
            total_count=total,
            emoji=progress_emoji(completed, total)
        ))
        d += timedelta(days=1)
    return result


@router.put("")
def upsert_record(update: RecordUpdate):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_records (date, task_id, completed, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date, task_id) DO UPDATE SET
            completed = excluded.completed,
            updated_at = excluded.updated_at
    """, (update.date.isoformat(), update.task_id, update.completed, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"message": "Record updated"}


@router.put("/batch")
def upsert_records_batch(updates: List[RecordUpdate]):
    conn = get_connection()
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
    conn.close()
    return {"message": f"Updated {len(updates)} records"}