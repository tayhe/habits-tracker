from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import clock, repo, weeks
from ..auth import get_current_user
from ..database import get_db
from ..models import DayRecords, RecordOut, RecordUpdate, TaskProgress, WeekRecords
from ..rules import assert_editable, progress_emoji

router = APIRouter(prefix="/records", tags=["records"])


def get_records_for_date(d: date) -> List[RecordOut]:
    """Get all tasks for a date, with completed=false for missing records."""
    d_str = d.isoformat()
    with get_db() as conn:
        task_rows = repo.get_active_tasks(conn)
        record_map = repo.get_daily_records_map(conn, d_str, d_str)
    return [
        RecordOut(
            date=d_str,
            task_id=t["task_id"],
            task_name=t["name"],
            subject=t["subject"],
            reward=t["reward"],
            completed=record_map.get((d_str, t["task_id"]), False),
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
        emoji=progress_emoji(completed, total),
    )


@router.get("", response_model=DayRecords)
def get_day_records(date: date = Query(...), user: dict = Depends(get_current_user)):
    records = get_records_for_date(date)
    return build_day_records(date, records)


@router.get("/range", response_model=List[DayRecords])
def get_range_records(
    start: date = Query(...),
    end: date = Query(...),
    user: dict = Depends(get_current_user),
):
    if end < start:
        raise HTTPException(status_code=400, detail="结束日期必须大于或等于开始日期")
    if (end - start).days > 93:
        raise HTTPException(status_code=400, detail="查询区间不能超过93天")

    with get_db() as conn:
        task_rows = repo.get_active_tasks(conn)
        record_map = repo.get_daily_records_map(conn, start.isoformat(), end.isoformat())

    result = []
    d = start
    while d <= end:
        d_str = d.isoformat()
        records = [
            RecordOut(
                date=d_str,
                task_id=t["task_id"],
                task_name=t["name"],
                subject=t["subject"],
                reward=t["reward"],
                completed=record_map.get((d_str, t["task_id"]), False),
            )
            for t in task_rows
        ]
        result.append(build_day_records(d, records))
        d += timedelta(days=1)
    return result


@router.get("/week", response_model=WeekRecords)
def get_week_records(
    date: date = Query(..., description="Any date in the target week"),
    user: dict = Depends(get_current_user),
):
    """Get all 7 days records for the week containing the given date."""
    monday = weeks.monday_of(date)
    sunday = weeks.sunday_of(date)
    week_str = weeks.iso_week_label(monday)
    week_start_str = monday.isoformat()
    week_end_str = (monday + timedelta(days=7)).isoformat()

    with get_db() as conn:
        all_tasks = repo.get_active_tasks(conn)
        task_ids = [t["task_id"] for t in all_tasks]
        record_map = repo.get_daily_records_map(conn, week_start_str, sunday.isoformat())
        counts = repo.get_completion_counts(conn, week_start_str, week_end_str, task_ids)

    days = []
    expected_earn = 0.0
    week_completed_days = 0

    for i in range(7):
        d = monday + timedelta(days=i)
        d_str = d.isoformat()
        records = [
            RecordOut(
                date=d_str,
                task_id=t["task_id"],
                task_name=t["name"],
                subject=t["subject"],
                reward=t["reward"],
                completed=record_map.get((d_str, t["task_id"]), False),
            )
            for t in all_tasks
        ]
        day_records = build_day_records(d, records)
        expected_earn += day_records.total_reward
        if day_records.total_count > 0 and day_records.completed_count >= day_records.total_count / 2:
            week_completed_days += 1
        days.append(day_records)

    task_progress = [
        TaskProgress(
            task_id=t["task_id"],
            name=t["name"],
            subject=t["subject"],
            reward=t["reward"],
            weekly_min=t["weekly_min"],
            completed_count=counts.get(t["task_id"], 0),
            qualified=counts.get(t["task_id"], 0) >= t["weekly_min"],
        )
        for t in all_tasks
    ]

    return WeekRecords(
        week=week_str,
        week_start=monday,
        week_end=sunday,
        days=days,
        expected_earn=round(expected_earn, 2),
        week_completed_days=week_completed_days,
        task_progress=task_progress,
    )


@router.put("")
def upsert_record(update: RecordUpdate, user: dict = Depends(get_current_user)):
    """Update a single record. Child users can only update records within the editable window."""
    assert_editable(user["role"], update.date)

    with get_db() as conn:
        task = repo.get_task_by_id(conn, update.task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务 '{update.task_id}' 不存在")

        repo.upsert_daily_record(
            conn,
            update.date.isoformat(),
            update.task_id,
            update.completed,
            clock.now().isoformat(),
        )
    return {"message": "Record updated"}


@router.put("/batch")
def upsert_records_batch(
    updates: List[RecordUpdate],
    user: dict = Depends(get_current_user),
):
    """Batch update records. Child users can only update records within the editable window."""
    for update in updates:
        assert_editable(user["role"], update.date)

    with get_db() as conn:
        task_ids = {u.task_id for u in updates}
        if task_ids:
            existing_ids = repo.get_existing_active_task_ids(conn, list(task_ids))
            missing = task_ids - existing_ids
            if missing:
                raise HTTPException(status_code=404, detail=f"任务不存在: {', '.join(sorted(missing))}")

        now = clock.now().isoformat()
        for update in updates:
            repo.upsert_daily_record(conn, update.date.isoformat(), update.task_id, update.completed, now)
    return {"message": f"Updated {len(updates)} records"}

