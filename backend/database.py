import logging
import shutil
import sqlite3
import subprocess
from contextlib import contextmanager

from . import clock, config

logger = logging.getLogger("habits.database")

# Current schema version, also stored in `PRAGMA user_version`.
SCHEMA_VERSION = 4


def get_connection():
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def backup_database_if_needed():
    """Backup database weekly and retain at most MAX_BACKUPS (oldest deleted)."""
    if not config.DB_PATH.exists():
        return None

    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    now = clock.now()
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
                logger.info("Created weekly backup: %s", backup_file.name)
            finally:
                dest_conn.close()
        finally:
            source_conn.close()

    # Prune older backups, keeping only the most recent MAX_BACKUPS
    backups = sorted(config.BACKUP_DIR.glob("habits_*_w*.db"), key=lambda p: p.name)
    if backups and len(backups) > config.MAX_BACKUPS:
        to_remove = backups[:-config.MAX_BACKUPS] if config.MAX_BACKUPS > 0 else backups
        trash_cmd = shutil.which("trash-put")
        for old_file in to_remove:
            removed = False
            if trash_cmd:
                try:
                    subprocess.run([trash_cmd, str(old_file)], check=True, capture_output=True)
                    removed = True
                except Exception:
                    pass
            if not removed:
                try:
                    old_file.unlink(missing_ok=True)
                    removed = True
                except Exception:
                    logger.exception("Failed to remove %s", old_file.name)
            if removed:
                logger.info("Pruned old backup: %s", old_file.name)

    return backup_file if created else None


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def _create_schema(cursor):
    """Create tables and indexes if they do not exist (idempotent baseline)."""
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
            subject TEXT NOT NULL,
            name TEXT NOT NULL,
            reward REAL NOT NULL DEFAULT 0,
            weekly_min INTEGER NOT NULL DEFAULT 1,
            sort_weight INTEGER NOT NULL DEFAULT 0,
            deleted_at DATETIME DEFAULT NULL,
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


# --- Schema migrations -------------------------------------------------------
# Each entry upgrades the schema FROM version N-1 TO version N.
# Add a new entry (and bump SCHEMA_VERSION) for every schema change; never edit
# an already-shipped migration. All migrations run in one transaction, before
# seeding, and are idempotent because they are only executed when user_version
# is behind.

def _migrate_to_v2(cursor):
    """v1 -> v2: soft delete / archive support for tasks."""
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]
    if "deleted_at" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN deleted_at DATETIME DEFAULT NULL")


def _migrate_to_v3(cursor):
    """v2 -> v3: restore daily_records(date, task_id) index (dropped in 2a643d1)."""
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_date_task ON daily_records(date, task_id)")


def _migrate_to_v4(cursor):
    """v3 -> v4: remove hardcoded CHECK constraint on tasks.subject."""
    cursor.execute("PRAGMA foreign_keys = OFF")
    cursor.execute("""
        CREATE TABLE tasks_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            subject TEXT NOT NULL,
            name TEXT NOT NULL,
            reward REAL NOT NULL DEFAULT 0,
            weekly_min INTEGER NOT NULL DEFAULT 1,
            sort_weight INTEGER NOT NULL DEFAULT 0,
            deleted_at DATETIME DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        INSERT INTO tasks_new (id, task_id, subject, name, reward, weekly_min, sort_weight, deleted_at, created_at)
        SELECT id, task_id, subject, name, reward, weekly_min, sort_weight, deleted_at, created_at
        FROM tasks
    """)
    cursor.execute("DROP TABLE tasks")
    cursor.execute("ALTER TABLE tasks_new RENAME TO tasks")
    cursor.execute("PRAGMA foreign_keys = ON")


MIGRATIONS = {
    2: _migrate_to_v2,
    3: _migrate_to_v3,
    4: _migrate_to_v4,
}


def _run_migrations(conn, cursor) -> None:
    cursor.execute("PRAGMA user_version")
    current = cursor.fetchone()[0]
    if current >= SCHEMA_VERSION:
        return
    for version in range(current + 1, SCHEMA_VERSION + 1):
        migrate = MIGRATIONS.get(version)
        if migrate is not None:
            migrate(cursor)
        # PRAGMA cannot be parameterized; `version` is an int from range().
        cursor.execute(f"PRAGMA user_version = {version}")
        conn.commit()
        logger.info("Schema migrated to version %d", version)


def _seed_initial_data(conn, cursor) -> None:
    """Seed default users and tasks, only when the tables are empty."""
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        import bcrypt

        users = [
            (config.INITIAL_PARENT_USERNAME, config.INITIAL_PARENT_PASSWORD, "parent"),
            (config.INITIAL_CHILD_USERNAME, config.INITIAL_CHILD_PASSWORD, "child"),
        ]
        for username, password, role in users:
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
            )
        conn.commit()
        if config.INITIAL_PARENT_PASSWORD == "parents" or config.INITIAL_CHILD_PASSWORD == "child":
            logger.warning(
                "Seeded default credentials; override INITIAL_PARENT_PASSWORD / "
                "INITIAL_CHILD_PASSWORD before exposing this service."
            )

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
            ("en_dictation", "英语", "听写", 0.5, 1, 3),
            ("math_course", "数学", "思维课程", 0.5, 2, 13),
            ("math_extra", "数学", "举一反三", 0.2, 5, 12),
            ("cn_morning", "语文", "晨读", 0.1, 4, 17),
            ("cn_read", "语文", "课外阅读", 0.2, 2, 16),
            ("cn_write", "语文", "书法", 0.1, 5, 15),
            ("cn_read100", "语文", "阅读100", 0.1, 2, 14),
            ("cn_dictation", "语文", "听写", 0.2, 1, 13),
            ("cn_note", "语文", "小纸条", 0.1, 5, 12),
            ("sport_5min", "体育", "体育5分钟", 0.2, 7, 20),
        ]
        cursor.executemany(
            "INSERT INTO tasks (task_id, subject, name, reward, weekly_min, sort_weight) VALUES (?, ?, ?, ?, ?, ?)",
            initial_tasks,
        )
        conn.commit()


def init_db():
    """Create schema, run pending migrations, then seed data."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        _create_schema(cursor)
        conn.commit()
        _run_migrations(conn, cursor)
        _seed_initial_data(conn, cursor)
    finally:
        conn.close()
    logger.info("Database initialized at %s", config.DB_PATH)


if __name__ == "__main__":
    init_db()
