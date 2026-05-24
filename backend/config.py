from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

PORT = 15000
DB_PATH = BASE_DIR / "data" / "habits.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

COOKIE_MAX_AGE = 60 * 60 * 24 * 30
SESSION_TOKEN_BYTES = 32
EDITABLE_DAY_WINDOW = 7
PROGRESS_EMOJI_THRESHOLDS = {"full": 1.0, "half": 0.5}
SUBJECTS = ["英语", "数学", "语文"]