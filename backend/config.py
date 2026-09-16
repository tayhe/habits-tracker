import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

PORT = int(os.getenv("PORT", 15000))
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "habits.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", DATA_DIR / "backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", 3))

COOKIE_MAX_AGE = int(os.getenv("COOKIE_MAX_AGE", 60 * 60 * 24 * 30))
EDITABLE_DAY_WINDOW = int(os.getenv("EDITABLE_DAY_WINDOW", 7))
SUBJECTS = ["英语", "数学", "语文"]