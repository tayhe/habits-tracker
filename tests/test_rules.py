from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from backend import config, database, rules, weeks


def test_reward_qualification_calculation():
    """Test core reward calculation rules in rules.py."""
    # Case 1: Below threshold
    assert rules.calculate_reward(reward=0.5, weekly_min=3, actual_completions=2) == 0.0
    # Case 2: Meets threshold exactly
    assert rules.calculate_reward(reward=0.5, weekly_min=3, actual_completions=3) == 1.5
    # Case 3: Exceeds threshold
    assert rules.calculate_reward(reward=0.5, weekly_min=3, actual_completions=5) == 2.5


def test_child_editable_window_rule():
    """Test assert_editable_for_child raises 403 when outside window."""
    today = date.today()
    # Child within window (6 days ago) -> no exception
    rules.assert_editable_for_child("child", today - timedelta(days=6), window_days=7)
    # Child outside window (7 days ago) -> 403
    with pytest.raises(HTTPException) as exc:
        rules.assert_editable_for_child("child", today - timedelta(days=7), window_days=7)
    assert exc.value.status_code == 403
    # Parent always allowed
    rules.assert_editable_for_child("parent", today - timedelta(days=30), window_days=7)


def test_iso_week_range_calculation():
    """Test ISO week range returns correct Monday and Sunday."""
    test_date = date(2026, 9, 16)
    monday = weeks.monday_of(test_date)
    sunday = weeks.sunday_of(test_date)
    assert monday == date(2026, 9, 14)
    assert sunday == date(2026, 9, 20)
    assert (sunday - monday).days == 6


def test_progress_emoji_display():
    """Test progress emoji threshold tiers."""
    assert rules.progress_emoji(0, 0) == "😿"
    assert rules.progress_emoji(0, 5) == "😿"
    assert rules.progress_emoji(1, 5) == "😾"
    assert rules.progress_emoji(2, 5) == "😼"
    assert rules.progress_emoji(3, 5) == "😸"
    assert rules.progress_emoji(4, 5) == "😺"
    assert rules.progress_emoji(5, 5) == "😺🎉"


def test_backup_pruning_keeps_max_three(tmp_path, monkeypatch):
    """Test that rolling backups retain strictly the most recent MAX_BACKUPS."""
    test_backup_dir = tmp_path / "backups"
    test_backup_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "BACKUP_DIR", test_backup_dir)
    monkeypatch.setattr(config, "MAX_BACKUPS", 3)

    # Create fake backup files
    for w in range(1, 6):
        (test_backup_dir / f"habits_2026_w{w:02d}.db").touch()

    # Trigger real backup pruning
    database.backup_database_if_needed()

    remaining = sorted([p.name for p in test_backup_dir.glob("habits_*_w*.db")])
    assert len(remaining) <= 3
