from datetime import date

import pytest
from fastapi import HTTPException

from backend import weeks


def test_t09_cross_year_iso_week_label():
    """T-09: 2025-12-29 belongs to 2026-W01 in ISO 8601."""
    d = date(2025, 12, 29)
    assert weeks.iso_week_label(d) == "2026-W01"

    d2 = date(2027, 1, 1)
    assert weeks.iso_week_label(d2) == "2026-W53"

def test_parse_week_label_roundtrip():
    """Verify parse_week_label roundtrip consistency."""
    test_cases = [
        ("2026-W21", date(2026, 5, 18), date(2026, 5, 24)),
        ("2026-W01", date(2025, 12, 29), date(2026, 1, 4)),
        ("2026-W53", date(2026, 12, 28), date(2027, 1, 3)),
        ("2027-W01", date(2027, 1, 4), date(2027, 1, 10)),
    ]
    for label, expected_mon, expected_sun in test_cases:
        monday, sunday = weeks.parse_week_label(label)
        assert monday == expected_mon
        assert sunday == expected_sun
        assert weeks.iso_week_label(monday) == label

def test_parse_week_label_invalid():
    """Out of range or malformed week strings must raise HTTPException(400)."""
    with pytest.raises(HTTPException) as exc:
        weeks.parse_week_label("2026-W99")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        weeks.parse_week_label("invalid-format")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        weeks.parse_week_label("2026-W00")
    assert exc.value.status_code == 400
