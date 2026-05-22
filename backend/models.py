from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


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


# --- Auth ---
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user: UserOut
    message: str


# --- Import ---
class CSVImportRequest(BaseModel):
    csv_content: str