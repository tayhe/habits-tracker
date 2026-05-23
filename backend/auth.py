import secrets
import bcrypt
from datetime import datetime, timedelta
from fastapi import HTTPException, Cookie, Depends
from typing import Optional
from database import get_db
import config


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
            (token, user_id, datetime.now().isoformat())
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
        if datetime.now() - created_at > timedelta(seconds=config.COOKIE_MAX_AGE):
            cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return None
        return {"id": row["user_id"], "username": row["username"], "role": row["role"]}


def delete_session(token: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


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
