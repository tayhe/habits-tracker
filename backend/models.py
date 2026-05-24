from pydantic import BaseModel
from typing import Optional
from datetime import date


# --- User ---
class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    password: str
    role: str = "child"


class UserOut(UserBase):
    id: int
    role: str

    class Config:
        from_attributes = True


# --- Task ---
class TaskBase(BaseModel):
    task_id: str
    subject: str
    name: str
    reward: float
    weekly_min: int = 1
    sort_weight: int = 0


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    reward: Optional[float] = None
    weekly_min: Optional[int] = None
    sort_weight: Optional[int] = None


class TaskOut(TaskBase):
    id: int

    class Config:
        from_attributes = True


# --- Daily Record ---
class RecordUpdate(BaseModel):
    date: date
    task_id: str
    completed: bool


class RecordOut(BaseModel):
    date: date
    task_id: str
    task_name: str
    subject: str
    reward: float
    completed: bool


class DayRecords(BaseModel):
    date: date
    records: list[RecordOut]
    total_reward: float
    completed_count: int
    total_count: int
    emoji: str


# --- Week Records ---
class TaskProgress(BaseModel):
    task_id: str
    name: str
    subject: str
    reward: float
    weekly_min: int
    completed_count: int
    qualified: bool


class WeekRecords(BaseModel):
    week_start: date  # Monday of the week
    week_end: date    # Sunday of the week
    days: list[DayRecords]  # 7 DayRecords, Monday to Sunday
    expected_earn: float
    week_completed_days: int
    task_progress: list[TaskProgress]


# --- Week Earn Summary ---
class WeekEarn(BaseModel):
    week: str  # e.g. "2026-W21"
    week_start: date
    week_end: date
    total_earn: float
    completed_days: int
    total_days: int = 7


# --- Auth ---
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user: UserOut
    message: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str