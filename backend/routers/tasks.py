import sqlite3
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from models import TaskCreate, TaskUpdate, TaskOut
from database import get_db
from auth import get_current_user, require_parent

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_all_tasks():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks ORDER BY sort_weight DESC")
        return [dict(row) for row in cursor.fetchall()]


@router.get("", response_model=List[TaskOut])
def list_tasks(user: dict = Depends(get_current_user)):
    tasks = get_all_tasks()
    return [
        TaskOut(
            id=t["id"],
            task_id=t["task_id"],
            subject=t["subject"],
            name=t["name"],
            reward=t["reward"],
            weekly_min=t["weekly_min"],
            sort_weight=t["sort_weight"]
        )
        for t in tasks
    ]


@router.post("")
def create_task(task: TaskCreate, user: dict = Depends(require_parent)):
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO tasks (task_id, subject, name, reward, weekly_min, sort_weight)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task.task_id, task.subject, task.name, task.reward, task.weekly_min, task.sort_weight)
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(status_code=400, detail=f"Task already exists or invalid data: {e}")
    return {"message": "Task created", "task_id": task.task_id}


@router.put("/{task_id}")
def update_task(task_id: str, task: TaskUpdate, user: dict = Depends(require_parent)):
    updates = []
    params = []
    if task.name is not None:
        updates.append("name = ?")
        params.append(task.name)
    if task.reward is not None:
        updates.append("reward = ?")
        params.append(task.reward)
    if task.weekly_min is not None:
        updates.append("weekly_min = ?")
        params.append(task.weekly_min)
    if task.sort_weight is not None:
        updates.append("sort_weight = ?")
        params.append(task.sort_weight)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    params.append(task_id)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?", params)
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return {"message": "Task updated"}


@router.delete("/{task_id}")
def delete_task(task_id: str, user: dict = Depends(require_parent)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return {"message": "Task deleted"}
