import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Cookie, Depends, HTTPException

from . import clock, config
from .database import get_db

logger = logging.getLogger("habits.auth")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def authenticate_user(username: str, password: str) -> dict | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return {"id": row["id"], "username": row["username"], "role": row["role"]}


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, clock.now_utc().isoformat()),
        )
        conn.commit()
    return token


def validate_session(token: str) -> dict | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.user_id, s.created_at, u.username, u.role
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token = ?
        """, (token,))
        row = cursor.fetchone()
        if not row:
            return None
        # Check session expiration
        created_at = datetime.fromisoformat(row["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if clock.now_utc() - created_at > timedelta(seconds=config.COOKIE_MAX_AGE):
            cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return None
        return {"id": row["user_id"], "username": row["username"], "role": row["role"]}


def delete_session(token: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def cleanup_expired_sessions():
    """Delete all sessions older than COOKIE_MAX_AGE.

    `julianday()` is used instead of string comparison so that legacy naive
    timestamps (`2026-09-30T12:00:00`) and new UTC ones
    (`2026-09-30T04:30:00+00:00`) are compared as instants, not as text.
    """
    cutoff = clock.now_utc() - timedelta(seconds=config.COOKIE_MAX_AGE)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM sessions WHERE julianday(created_at) < julianday(?)",
            (cutoff.isoformat(),),
        )
        deleted = cursor.rowcount
        conn.commit()
    if deleted > 0:
        logger.info("Cleaned up %d expired session(s)", deleted)
    return deleted


# --- Auth dependencies for FastAPI ---
def get_current_user(session_token: Optional[str] = Cookie(None)) -> dict:
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = validate_session(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


def require_parent(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "parent":
        raise HTTPException(status_code=403, detail="Parent access required")
    return user
