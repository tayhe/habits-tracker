import time
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

from .. import auth, config
from ..auth import get_current_user
from ..models import ChangePasswordRequest, LoginRequest, LoginResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

class BoundedRateLimiter:
    """In-memory rate limiter with bounded keys and dual IP/User limits.

    Assumes single-process deployment.
    """

    def __init__(
        self,
        max_keys: int = 1000,
        window_seconds: int = 60,
        max_ip_attempts: int = 30,
        max_pair_attempts: int = 5,
    ):
        self.max_keys = max_keys
        self.window_seconds = window_seconds
        self.max_ip_attempts = max_ip_attempts
        self.max_pair_attempts = max_pair_attempts
        self._attempts: dict[str, list[float]] = {}

    def _prune(self, now: float) -> None:
        expired = [
            k for k, times in self._attempts.items()
            if not times or now - times[-1] >= self.window_seconds
        ]
        for k in expired:
            del self._attempts[k]
        if len(self._attempts) > self.max_keys:
            excess = len(self._attempts) - self.max_keys
            for k in list(self._attempts.keys())[:excess]:
                del self._attempts[k]

    def check(self, ip: str, username: str) -> None:
        now = time.time()
        self._prune(now)

        ip_times = [t for t in self._attempts.get(f"ip:{ip}", []) if now - t < self.window_seconds]
        if len(ip_times) >= self.max_ip_attempts:
            raise HTTPException(status_code=429, detail="登录尝试过多，请在 1 分钟后重试")

        pair_times = [
            t for t in self._attempts.get(f"pair:{ip}:{username}", [])
            if now - t < self.window_seconds
        ]
        if len(pair_times) >= self.max_pair_attempts:
            raise HTTPException(status_code=429, detail="登录尝试过多，请在 1 分钟后重试")

    def record_failure(self, ip: str, username: str) -> None:
        now = time.time()
        self._attempts.setdefault(f"ip:{ip}", []).append(now)
        self._attempts.setdefault(f"pair:{ip}:{username}", []).append(now)

    def record_success(self, ip: str, username: str) -> None:
        self._attempts.pop(f"pair:{ip}:{username}", None)


limiter = BoundedRateLimiter()


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, response: Response, req: Request):
    client_ip = req.client.host if req.client else "unknown"
    limiter.check(client_ip, request.username)

    user = auth.authenticate_user(request.username, request.password)
    if not user:
        limiter.record_failure(client_ip, request.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    limiter.record_success(client_ip, request.username)
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

