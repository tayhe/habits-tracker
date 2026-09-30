#!/usr/bin/env python3
"""Print canonical outputs of the *Python* date/week/emoji logic.

`scripts/parity_check.sh` diffs this against `scripts/parity_frontend.mjs`,
which produces the same lines from the *browser* implementation
(frontend/lib/*.js). Any drift between the two stacks fails the diff.

Run directly for a human-readable dump:
    .venv/bin/python scripts/parity_backend.py | less
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402

from backend import rules, weeks  # noqa: E402

START = date(2020, 1, 1)
DAYS = 1500
YEAR_RANGE = range(2020, 2031)


def lines() -> list[str]:
    out: list[str] = []

    # 1) ISO week label + Monday/Sunday range for 1500 consecutive days.
    d = START
    for _ in range(DAYS):
        out.append(
            f"week {d.isoformat()} {weeks.iso_week_label(d)} "
            f"{weeks.monday_of(d).isoformat()} {weeks.sunday_of(d).isoformat()}"
        )
        d += timedelta(days=1)

    # 2) Week-label parsing, including rejection of out-of-range week numbers.
    for year in YEAR_RANGE:
        for week in range(1, 53):
            label = f"{year}-W{week:02d}"
            try:
                monday, sunday = weeks.parse_week_label(label)
            except HTTPException:
                out.append(f"parse {label} invalid")
            else:
                out.append(f"parse {label} ok {monday.isoformat()} {sunday.isoformat()}")

    # 3) Progress emoji tiers over the full (completed, total) grid.
    for total in range(0, 17):
        for completed in range(0, total + 1):
            out.append(f"emoji {completed}/{total} {rules.progress_emoji(completed, total)}")

    return out


if __name__ == "__main__":
    print("\n".join(lines()))
