from fastapi import FastAPI, HTTPException, Response, Cookie, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
import auth
import database
from routers import tasks, records, summary
from models import LoginRequest, LoginResponse, UserOut

database.init_db()

app = FastAPI(title="Habits Tracker API", version="1.0.0")

# CORS - allow all for局域网
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(records.router, prefix="/api/v1")
app.include_router(summary.router, prefix="/api/v1")

# Serve frontend at /app
import os
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/app", StaticFiles(directory=frontend_path, html=True), name="frontend")

# Redirect root to /app
@app.get("/")
def root():
    import os
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=f.read())
    return {"message": "Habits Tracker API", "version": "1.0.0"}


# --- Auth dependencies ---
def get_current_user(token: Optional[str] = Cookie(None)) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = auth.validate_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


def require_parent(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "parent":
        raise HTTPException(status_code=403, detail="Parent access required")
    return user


# --- Auth routes ---
@app.post("/api/v1/auth/login", response_model=LoginResponse)
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
        max_age=60 * 60 * 24 * 30  # 30 days
    )
    return LoginResponse(
        user=UserOut(id=user["id"], username=user["username"], role=user["role"]),
        message="Login successful"
    )


@app.post("/api/v1/auth/logout")
def logout(response: Response, token: Optional[str] = Cookie(None)):
    if token:
        auth.delete_session(token)
    response.delete_cookie("session_token")
    return {"message": "Logged out"}


@app.get("/api/v1/auth/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return UserOut(id=user["id"], username=user["username"], role=user["role"])


# --- Health check ---
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "Habits Tracker API", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18765)