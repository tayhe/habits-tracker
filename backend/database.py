import sqlite3
import shutil
import subprocess
from datetime import datetime
from contextlib import contextmanager

from . import config

DB_PATH = config.DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def backup_database_if_needed():
    """Backup database weekly and retain at most MAX_BACKUPS (oldest deleted)."""
    if not DB_PATH.exists():
        return None

    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    iso_year, iso_week, _ = now.isocalendar()
    backup_name = f"habits_{iso_year}_w{iso_week:02d}.db"
    backup_file = config.BACKUP_DIR / backup_name

    created = False
    if not backup_file.exists():
        source_conn = get_connection()
        try:
            dest_conn = sqlite3.connect(str(backup_file))
            try:
                source_conn.backup(dest_conn)
                created = True
                print(f"[Backup] Created weekly backup: {backup_file.name}")
            finally:
                dest_conn.close()
        finally:
            source_conn.close()

    # Prune older backups, keeping only the most recent MAX_BACKUPS
    backups = sorted(config.BACKUP_DIR.glob("habits_*_w*.db"), key=lambda p: p.name)
    if len(backups) > config.MAX_BACKUPS:
        to_remove = backups[:-config.MAX_BACKUPS]
        trash_cmd = shutil.which("trash-put")
        for old_file in to_remove:
            try:
                if trash_cmd:
                    subprocess.run([trash_cmd, str(old_file)], check=True)
                else:
                    old_file.unlink(missing_ok=True)
                print(f"[Backup] Pruned old backup: {old_file.name}")
            except Exception as e:
                print(f"[Backup] Failed to remove {old_file.name}: {e}")

    return backup_file if created else None


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database tables and seed data."""
    conn = get_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('parent', 'child')),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            subject TEXT NOT NULL CHECK(subject IN ('英语', '数学', '语文')),
            name TEXT NOT NULL,
            reward REAL NOT NULL DEFAULT 0,
            weekly_min INTEGER NOT NULL DEFAULT 1,
            sort_weight INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Daily records table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            task_id TEXT NOT NULL,
            completed BOOLEAN NOT NULL DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(task_id),
            UNIQUE(date, task_id)
        )
    """)

    # Sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Weekly fulfillment table (爸爸兑现)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weekly_fulfillment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week TEXT UNIQUE NOT NULL,
            fulfilled BOOLEAN NOT NULL DEFAULT 0,
            fulfilled_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes for query performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_date_task ON daily_records(date, task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")

    conn.commit()

    # Seed users if not exist
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        import bcrypt
        parent_hash = bcrypt.hashpw("parents".encode(), bcrypt.gensalt()).decode()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("tayhe", parent_hash, "parent")
        )
        child_hash = bcrypt.hashpw("child".encode(), bcrypt.gensalt()).decode()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("meow", child_hash, "child")
        )
        conn.commit()

    # Seed tasks if not exist
    cursor.execute("SELECT COUNT(*) FROM tasks")
    if cursor.fetchone()[0] == 0:
        initial_tasks = [
            ("en_word", "英语", "单词", 0.1, 5, 10),
            ("en_picture", "英语", "绘本", 0.2, 5, 9),
            ("en_recite", "英语", "背诵", 1.0, 1, 8),
            ("en_class", "英语", "课", 0.3, 5, 7),
            ("en_listen", "英语", "听力", 0.1, 5, 6),
            ("en_read100", "英语", "阅读100", 0.2, 2, 5),
            ("en_grammar", "英语", "语法", 0.5, 2, 4),
            ("math_course", "数学", "思维课程", 0.5, 2, 13),
            ("math_extra", "数学", "举一反三", 0.2, 5, 12),
            ("math_prac", "数学", "预习课后练习", 0.2, 4, 11),
            ("math_calc", "数学", "计算", 0.2, 5, 10),
            ("cn_morning", "语文", "晨读", 0.1, 4, 17),
            ("cn_read", "语文", "课外阅读", 0.2, 2, 16),
            ("cn_write", "语文", "书法", 0.1, 5, 15),
            ("cn_read100", "语文", "阅读100", 0.1, 5, 14),
        ]
        cursor.executemany(
            "INSERT INTO tasks (task_id, subject, name, reward, weekly_min, sort_weight) VALUES (?, ?, ?, ?, ?, ?)",
            initial_tasks
        )
        conn.commit()

    # Schema versioning
    cursor.execute("PRAGMA user_version")
    current_version = cursor.fetchone()[0]
    if current_version == 0:
        cursor.execute("PRAGMA user_version = 1")
        conn.commit()

    conn.close()
    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()