from fastapi import APIRouter, HTTPException, Response, Cookie, Depends
from typing import Optional
import auth
import config
from models import LoginRequest, LoginResponse, UserOut, ChangePasswordRequest
from auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, response: Response):
    user = auth.authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
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
def logout(response: Response, token: Optional[str] = Cookie(None)):
    if token:
        auth.delete_session(token)
    response.delete_cookie("session_token")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return UserOut(id=user["id"], username=user["username"], role=user["role"])


@router.put("/password")
def change_password(request: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    from database import get_db
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
        conn.commit()
    return {"message": "密码修改成功"}
