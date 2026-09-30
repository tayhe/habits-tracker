import sqlite3
from datetime import date
from typing import Optional

from . import weeks


def get_active_tasks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all active (non-archived) tasks ordered by sort_weight DESC, id ASC."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, task_id, name, subject, reward, weekly_min, sort_weight
        FROM tasks
        WHERE deleted_at IS NULL
        ORDER BY sort_weight DESC, id ASC
    """)
    return cursor.fetchall()


def get_task_by_id(conn: sqlite3.Connection, task_id: str, include_deleted: bool = False) -> Optional[sqlite3.Row]:
    """Get a task by task_id."""
    cursor = conn.cursor()
    if include_deleted:
        cursor.execute("SELECT id, task_id, name, subject, reward, weekly_min, sort_weight, deleted_at FROM tasks WHERE task_id = ?", (task_id,))
    else:
        cursor.execute("SELECT id, task_id, name, subject, reward, weekly_min, sort_weight FROM tasks WHERE task_id = ? AND deleted_at IS NULL", (task_id,))
    return cursor.fetchone()


def get_existing_active_task_ids(conn: sqlite3.Connection, task_ids: list[str]) -> set[str]:
    """Return the subset of `task_ids` that exist and are not archived."""
    if not task_ids:
        return set()
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(task_ids))
    cursor.execute(
        f"SELECT task_id FROM tasks WHERE task_id IN ({placeholders}) AND deleted_at IS NULL",
        list(task_ids),
    )
    return {row["task_id"] for row in cursor.fetchall()}


def get_completion_counts_by_week(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    task_ids: list[str],
) -> dict[tuple[str, str], int]:
    """Count completed records per (ISO week label, task) over [start_date, end_date).

    One query covers the whole span; the ISO week is derived in Python with
    `weeks.iso_week_label`, so bucketing can never disagree with the weekly
    endpoints that use the same function.
    """
    if not task_ids:
        return {}
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(task_ids))
    cursor.execute(f"""
        SELECT date, task_id, COUNT(*) as cnt
        FROM daily_records
        WHERE completed = 1 AND date >= ? AND date < ?
          AND task_id IN ({placeholders})
        GROUP BY date, task_id
    """, [start_date, end_date] + task_ids)
    counts: dict[tuple[str, str], int] = {}
    for row in cursor.fetchall():
        week = weeks.iso_week_label(date.fromisoformat(row["date"]))
        key = (week, row["task_id"])
        counts[key] = counts.get(key, 0) + row["cnt"]
    return counts


def get_completion_counts(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    task_ids: list[str]
) -> dict[str, int]:
    """Count completed daily records per task in date range [start_date, end_date).

    Thin aggregation over `get_completion_counts_by_week` so both share one
    filter definition.
    """
    totals: dict[str, int] = {}
    for (_week, task_id), cnt in get_completion_counts_by_week(
        conn, start_date, end_date, task_ids
    ).items():
        totals[task_id] = totals.get(task_id, 0) + cnt
    return totals


def get_daily_records_map(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str
) -> dict[tuple[str, str], bool]:
    """Return mapping of (date, task_id) -> completed for date range [start_date, end_date]."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date, task_id, completed
        FROM daily_records
        WHERE date >= ? AND date <= ?
    """, (start_date, end_date))
    return {(row["date"], row["task_id"]): bool(row["completed"]) for row in cursor.fetchall()}


def upsert_daily_record(
    conn: sqlite3.Connection,
    date_str: str,
    task_id: str,
    completed: bool,
    updated_at: str
) -> None:
    """Insert or update a daily completion record."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_records (date, task_id, completed, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date, task_id) DO UPDATE SET
            completed = excluded.completed,
            updated_at = excluded.updated_at
    """, (date_str, task_id, completed, updated_at))
