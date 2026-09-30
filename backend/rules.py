from datetime import date, timedelta

from fastapi import HTTPException

from . import clock, config


def progress_emoji(completed_count: int, total_count: int) -> str:
    """Calculate pet cat emoji according to completion rate."""
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


def calculate_reward(reward: float, weekly_min: int, actual_completions: int) -> float:
    """Calculate confirmed weekly reward: if actual >= weekly_min, reward * actual; else 0."""
    if actual_completions >= weekly_min:
        return round(reward * actual_completions, 2)
    return 0.0


def assert_editable(role: str, target_date: date, window_days: int | None = None) -> None:
    """Assert the requesting role is allowed to write a record for `target_date`.

    Rules (see README 权限矩阵):
    - nobody (parent included) may punch a **future** date;
    - `child` may only touch the last `window_days` days, `parent` any past date.
    """
    if window_days is None:
        window_days = config.EDITABLE_DAY_WINDOW
    current_date = clock.today()
    if role == "child":
        editable_start = current_date - timedelta(days=window_days - 1)
        if target_date < editable_start or target_date > current_date:
            raise HTTPException(
                status_code=403,
                detail=f"小朋友只能修改最近 {window_days} 天的打卡记录"
            )
    elif target_date > current_date:
        raise HTTPException(
            status_code=400,
            detail="打卡日期不能超过今天"
        )
