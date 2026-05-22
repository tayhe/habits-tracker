from fastapi import APIRouter, HTTPException, Depends
from typing import List
from models import TaskCreate, TaskUpdate, TaskOut
from database import get_connection

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_all_tasks():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks ORDER BY sort_weight DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.get("", response_model=List[TaskOut])
def list_tasks():
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
def create_task(task: TaskCreate):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO tasks (task_id, subject, name, reward, weekly_min, sort_weight)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task.task_id, task.subject, task.name, task.reward, task.weekly_min, task.sort_weight)
        )
        conn.commit()
        return {"message": "Task created", "task_id": task.task_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.put("/{task_id}")
def update_task(task_id: str, task: TaskUpdate):
    conn = get_connection()
    cursor = conn.cursor()
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
    cursor.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?", params)
    conn.commit()
    conn.close()
    return {"message": "Task updated"}


@router.delete("/{task_id}")
def delete_task(task_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"message": "Task deleted"}