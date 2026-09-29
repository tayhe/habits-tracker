from datetime import date, timedelta

from fastapi import HTTPException


def monday_of(d: date) -> date:
    """Return the Monday of the ISO week containing date d."""
    return d - timedelta(days=d.weekday())


def sunday_of(d: date) -> date:
    """Return the Sunday of the ISO week containing date d."""
    return monday_of(d) + timedelta(days=6)


def iso_week_label(d: date) -> str:
    """Return ISO 8601 week string (e.g. '2026-W21').

    Guarantees that the ISO year matches the ISO week number.
    """
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def parse_week_label(week_str: str) -> tuple[date, date]:
    """Parse 'YYYY-WXX' into (monday, sunday) of that ISO week.

    Raises HTTPException(400) if format is invalid or week number is out of range.
    """
    if not isinstance(week_str, str) or "-W" not in week_str:
        raise HTTPException(status_code=400, detail="Invalid week format, use YYYY-WXX")

    parts = week_str.split("-W")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid week format, use YYYY-WXX")

    try:
        year = int(parts[0])
        week_num = int(parts[1])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid week format, year and week must be numbers")

    if year < 1970 or year > 2100:
        raise HTTPException(status_code=400, detail=f"Year {year} out of supported range")

    # In ISO 8601, Dec 28 is always in the last week of the year
    last_week_of_year = date(year, 12, 28).isocalendar()[1]
    if week_num < 1 or week_num > last_week_of_year:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid week number {week_num} for year {year} (valid: 1..{last_week_of_year})"
        )

    try:
        monday = date.fromisocalendar(year, week_num, 1)
        sunday = date.fromisocalendar(year, week_num, 7)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid ISO week: {e}")

    return monday, sunday
