from datetime import date, timedelta

from fastapi import HTTPException

from . import config


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


def progress_bar(completed: int, total: int, max_len: int = 15) -> str:
    """Render a text progress bar."""
    if total == 0:
        return "░" * min(4, max_len)
    length = min(total, max_len)
    filled = round((completed / total) * length)
    return "▓" * filled + "░" * (length - filled)


def calculate_reward(reward: float, weekly_min: int, actual_completions: int) -> float:
    """Calculate confirmed weekly reward: if actual >= weekly_min, reward * actual; else 0."""
    if actual_completions >= weekly_min:
        return round(reward * actual_completions, 2)
    return 0.0


def assert_editable_for_child(role: str, target_date: date, window_days: int = None) -> None:

    """Assert child user can only edit within editable window."""
    if role == "child":
        if window_days is None:
            window_days = config.EDITABLE_DAY_WINDOW
        today = date.today()
        editable_start = today - timedelta(days=window_days - 1)
        if target_date < editable_start or target_date > today:
            raise HTTPException(
                status_code=403,
                detail=f"小朋友只能修改最近 {window_days} 天的打卡记录"
            )
