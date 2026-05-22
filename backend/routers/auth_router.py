from fastapi import APIRouter, HTTPException, Response, Cookie, Depends
from typing import Optional
import auth
import config
from models import LoginRequest, LoginResponse, UserOut
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
