import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

from .. import auth, config
from ..auth import get_current_user
from ..models import ChangePasswordRequest, LoginRequest, LoginResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

_login_attempts = defaultdict(list)


def _check_rate_limit(key: str, max_attempts: int = 5, window_seconds: int = 60):
    now = time.time()
    attempts = [t for t in _login_attempts[key] if now - t < window_seconds]
    _login_attempts[key] = attempts
    if len(attempts) >= max_attempts:
        raise HTTPException(
            status_code=429,
            detail="登录尝试过多，请在 1 分钟后重试"
        )


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, response: Response, req: Request):
    client_ip = req.client.host if req.client else "unknown"
    limit_key = f"{client_ip}:{request.username}"
    _check_rate_limit(limit_key)

    user = auth.authenticate_user(request.username, request.password)
    if not user:
        _login_attempts[limit_key].append(time.time())
        raise HTTPException(status_code=401, detail="Invalid username or password")

    _login_attempts.pop(limit_key, None)
    token = auth.create_session(user["id"])
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=config.COOKIE_MAX_AGE
    )
    return LoginResponse(
        user=UserOut(id=user["id"], username=user["username"], role=user["role"]),
        message="Login successful"
    )



@router.post("/logout")
def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    if session_token:
        auth.delete_session(session_token)
    response.delete_cookie("session_token")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return UserOut(id=user["id"], username=user["username"], role=user["role"])


@router.put("/password")
def change_password(request: ChangePasswordRequest, response: Response, user: dict = Depends(get_current_user)):
    from ..database import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        if not auth.verify_password(request.old_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="当前密码错误")
        if len(request.new_password) < 6:
            raise HTTPException(status_code=400, detail="新密码至少需要6个字符")
        new_hash = auth.hash_password(request.new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
        conn.commit()

    # Reissue new session token for the current client
    new_token = auth.create_session(user["id"])
    response.set_cookie(
        key="session_token",
        value=new_token,
        httponly=True,
        samesite="lax",
        max_age=config.COOKIE_MAX_AGE
    )
    return {"message": "密码修改成功"}

