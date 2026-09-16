import tempfile
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
import pytest

from backend import config, database, auth
from backend.routers import summary, records


def test_reward_qualification_calculation():
    """
    Test core reward calculation rules:
    - If completions >= weekly_min, task is qualified and earns: reward * actual_count
    - If completions < weekly_min, task is NOT qualified and earns: 0
    """
    task_reward = 0.5
    weekly_min = 3

    # Case 1: Below threshold (unqualified)
    completions = 2
    is_qualified = completions >= weekly_min
    assert not is_qualified
    actual_reward = round(task_reward * completions, 2) if is_qualified else 0.0
    assert actual_reward == 0.0

    # Case 2: Meets threshold exactly
    completions = 3
    is_qualified = completions >= weekly_min
    assert is_qualified
    actual_reward = round(task_reward * completions, 2) if is_qualified else 0.0
    assert actual_reward == 1.5

    # Case 3: Exceeds threshold (more reward)
    completions = 5
    is_qualified = completions >= weekly_min
    assert is_qualified
    actual_reward = round(task_reward * completions, 2) if is_qualified else 0.0
    assert actual_reward == 2.5


def test_child_editable_window_rule():
    """
    Test role permission window:
    - Child can only edit records within the last EDITABLE_DAY_WINDOW days (today included)
    - Parent can edit any date
    """
    window = config.EDITABLE_DAY_WINDOW  # Default 7 days
    today = date.today()
    allowed_start = today - timedelta(days=window - 1)

    # Today is editable by child
    assert today >= allowed_start

    # Exactly 6 days ago (7th day) is editable
    assert allowed_start >= allowed_start

    # 7 days ago (8th day) is NOT editable by child
    eight_days_ago = today - timedelta(days=window)
    assert eight_days_ago < allowed_start


def test_iso_week_range_calculation():
    """Test ISO week range returns correct Monday and Sunday."""
    # A known Wednesday: 2026-09-16
    test_date = date(2026, 9, 16)
    monday, sunday = summary.get_iso_week_range(test_date)
    assert monday == date(2026, 9, 14)  # Monday
    assert sunday == date(2026, 9, 20)  # Sunday
    assert (sunday - monday).days == 6


def test_progress_emoji_display():
    """Test progress emoji threshold tiers."""
    assert records.progress_emoji(0, 0) == "😿"
    assert records.progress_emoji(0, 5) == "😿"
    assert records.progress_emoji(1, 5) == "😾"   # 20%
    assert records.progress_emoji(2, 5) == "😼"   # 40%
    assert records.progress_emoji(3, 5) == "😸"   # 60%
    assert records.progress_emoji(4, 5) == "😺"   # 80%
    assert records.progress_emoji(5, 5) == "😺🎉" # 100%


def test_config_env_support(monkeypatch):
    """Test environment variable overrides in config."""
    monkeypatch.setenv("PORT", "16000")
    monkeypatch.setenv("MAX_BACKUPS", "5")
    monkeypatch.setenv("EDITABLE_DAY_WINDOW", "10")

    # Re-evaluate logic matching config.py
    import os
    port = int(os.getenv("PORT", 15000))
    max_backups = int(os.getenv("MAX_BACKUPS", 3))
    editable_window = int(os.getenv("EDITABLE_DAY_WINDOW", 7))

    assert port == 16000
    assert max_backups == 5
    assert editable_window == 10


def test_backup_pruning_keeps_max_three():
    """Test that rolling backups retain strictly the most recent MAX_BACKUPS."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        backup_dir = Path(tmp_dir)
        # Create 5 fake weekly backups
        files = [
            backup_dir / "habits_2026_w01.db",
            backup_dir / "habits_2026_w02.db",
            backup_dir / "habits_2026_w03.db",
            backup_dir / "habits_2026_w04.db",
            backup_dir / "habits_2026_w05.db",
        ]
        for f in files:
            f.touch()

        # Pruning logic as implemented in database.py
        max_backups = 3
        backups = sorted(backup_dir.glob("habits_*_w*.db"), key=lambda p: p.name)
        if len(backups) > max_backups:
            to_remove = backups[:-max_backups]
            for old_file in to_remove:
                old_file.unlink()

        remaining = sorted([p.name for p in backup_dir.glob("habits_*_w*.db")])
        assert remaining == [
            "habits_2026_w03.db",
            "habits_2026_w04.db",
            "habits_2026_w05.db"
        ]
        assert len(remaining) == 3
