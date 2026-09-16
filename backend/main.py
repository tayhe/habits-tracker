import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from . import database, config, auth
from .routers import tasks, records, summary, auth_router


async def periodic_maintenance():
    """Background task to run backup check and session cleanup daily."""
    while True:
        try:
            database.backup_database_if_needed()
            auth.cleanup_expired_sessions()
        except Exception as e:
            print(f"[Maintenance Error] {e}")
        await asyncio.sleep(24 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    database.backup_database_if_needed()
    auth.cleanup_expired_sessions()
    task = asyncio.create_task(periodic_maintenance())
    yield
    task.cancel()


app = FastAPI(title="Habits Tracker API", version="1.0.0", lifespan=lifespan)

# CORS - allow all for LAN access (no credentials needed since frontend is same-origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(records.router, prefix="/api/v1")
app.include_router(summary.router, prefix="/api/v1")

# Serve frontend
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/app", StaticFiles(directory=frontend_path, html=True), name="frontend")


@app.get("/")
def root():
    index_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return {"message": "Habits Tracker API", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/config")
def get_config():
    return {"editable_day_window": config.EDITABLE_DAY_WINDOW}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
