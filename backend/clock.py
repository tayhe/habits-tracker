from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

_mock_now: Optional[datetime] = None


def now() -> datetime:
    """Return current timezone-aware datetime in Asia/Shanghai (or mock if set)."""
    if _mock_now is not None:
        if _mock_now.tzinfo is None:
            return _mock_now.replace(tzinfo=SHANGHAI_TZ)
        return _mock_now.astimezone(SHANGHAI_TZ)
    return datetime.now(SHANGHAI_TZ)


def today() -> date:
    """Return current date in Asia/Shanghai (or mock if set)."""
    return now().date()


def now_utc() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return now().astimezone(timezone.utc)


def set_mock_time(dt: Optional[datetime]) -> None:
    """Set or clear mock time for tests."""
    global _mock_now
    _mock_now = dt
