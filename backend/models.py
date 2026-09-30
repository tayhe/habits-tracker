from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import config


# --- User ---
class UserBase(BaseModel):
    username: str


class UserOut(UserBase):
    id: int
    role: str

    model_config = ConfigDict(from_attributes=True)


# --- Task ---
class TaskBase(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=50)
    subject: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=50)
    reward: float = Field(0.0, ge=0, le=1000)
    weekly_min: int = Field(1, ge=1, le=30)
    sort_weight: int = Field(0, ge=0, le=1000)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str) -> str:
        if v not in config.SUBJECTS:
            raise ValueError(f"科目无效，必须是以下之一: {', '.join(config.SUBJECTS)}")
        return v


class TaskCreate(TaskBase):
    # `reward` / `weekly_min` MUST stay required here: TaskBase carries defaults
    # only so that TaskOut can round-trip rows from the DB. If they were optional
    # on create, a missing field would silently become 0 / 1 instead of a 422.
    reward: float = Field(..., ge=0, le=1000)
    weekly_min: int = Field(..., ge=1, le=30)

    model_config = ConfigDict(extra="forbid")


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    subject: Optional[str] = Field(None, min_length=1, max_length=20)
    reward: Optional[float] = Field(None, ge=0, le=1000)
    weekly_min: Optional[int] = Field(None, ge=1, le=30)
    sort_weight: Optional[int] = Field(None, ge=0, le=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in config.SUBJECTS:
            raise ValueError(f"科目无效，必须是以下之一: {', '.join(config.SUBJECTS)}")
        return v

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, values: dict):
        if not isinstance(values, dict):
            return values
        for k in ("name", "subject", "reward", "weekly_min", "sort_weight"):
            if k in values and values[k] is None:
                raise ValueError(f"字段 '{k}' 不能为 null")
        return values


class TaskOut(TaskBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# --- Daily Record ---
class RecordUpdate(BaseModel):
    date: date
    task_id: str
    completed: bool

    model_config = ConfigDict(extra="forbid")


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
    week: str = ""    # e.g. "2026-W21"
    week_start: date  # Monday of the week
    week_end: date    # Sunday of the week
    days: list[DayRecords]  # 7 DayRecords, Monday to Sunday
    expected_earn: float
    week_completed_days: int
    task_progress: list[TaskProgress]


# --- Auth ---
class LoginRequest(BaseModel):
    username: str
    password: str

    model_config = ConfigDict(extra="forbid")


class LoginResponse(BaseModel):
    user: UserOut
    message: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    model_config = ConfigDict(extra="forbid")
