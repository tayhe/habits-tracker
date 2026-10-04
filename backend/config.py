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
SUBJECTS = ["英语", "数学", "语文", "体育"]

# --- Initial credentials (seeded only when the users table is empty) ---
# Always override in production: INITIAL_PARENT_PASSWORD=... docker compose up -d
INITIAL_PARENT_USERNAME = os.getenv("INITIAL_PARENT_USERNAME", "tayhe")
INITIAL_PARENT_PASSWORD = os.getenv("INITIAL_PARENT_PASSWORD", "parents")
INITIAL_CHILD_USERNAME = os.getenv("INITIAL_CHILD_USERNAME", "meow")
INITIAL_CHILD_PASSWORD = os.getenv("INITIAL_CHILD_PASSWORD", "child")


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# --- API surface hardening ---
# Interactive API docs are off by default; set ENABLE_DOCS=1 for local development.
ENABLE_DOCS = _env_flag("ENABLE_DOCS")
# Cross-origin access is off by default because the SPA is served same-origin.
# Set CORS_ORIGINS="https://a.example,https://b.example" only if you split the frontend.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# --- Background maintenance ---
# Backup / session cleanup runs at this hour (Asia/Shanghai) every day.
MAINTENANCE_HOUR = int(os.getenv("MAINTENANCE_HOUR", 3))
