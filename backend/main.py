import asyncio
import contextlib
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, clock, config, database
from .routers import auth_router, records, summary, tasks

logger = logging.getLogger("habits")

# Idempotent: no-op when the host (uvicorn/pytest) already configured logging.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Basic hardening headers applied to every response. `unsafe-eval` / `unsafe-inline`
# for script/style are required by the zero-build Vue full build (in-DOM template
# compilation) — verified in the browser smoke test.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "manifest-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    ),
}


def seconds_until_next_maintenance(hour: int | None = None) -> float:
    """Seconds until the next daily maintenance run at `hour` (Asia/Shanghai)."""
    hour = config.MAINTENANCE_HOUR if hour is None else hour
    now = clock.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


async def periodic_maintenance():
    """Run backup check + session cleanup once a day, aligned to MAINTENANCE_HOUR."""
    while True:
        try:
            database.backup_database_if_needed()
            auth.cleanup_expired_sessions()
        except Exception:
            logger.exception("Periodic maintenance failed")
        try:
            await asyncio.sleep(seconds_until_next_maintenance())
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never let a scheduling error kill the loop.
            logger.exception("Maintenance sleep failed; retrying in 1 hour")
            await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    database.backup_database_if_needed()
    auth.cleanup_expired_sessions()
    task = asyncio.create_task(periodic_maintenance())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(
    title="Habits Tracker API",
    version="1.0.0",
    lifespan=lifespan,
    # Interactive API docs are disabled by default (set ENABLE_DOCS=1 to enable).
    docs_url="/docs" if config.ENABLE_DOCS else None,
    redoc_url="/redoc" if config.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if config.ENABLE_DOCS else None,
)


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error_handler(request, exc):
    return JSONResponse(
        status_code=409,
        content={"detail": f"数据完整性冲突: {str(exc)}"},
    )


@app.exception_handler(sqlite3.OperationalError)
async def operational_error_handler(request, exc):
    if "locked" in str(exc).lower():
        return JSONResponse(
            status_code=503,
            content={"detail": "数据库忙，请稍后重试"},
        )
    return JSONResponse(
        status_code=500,
        content={"detail": f"数据库操作异常: {str(exc)}"},
    )


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


# CORS is disabled unless explicitly configured: the SPA is served same-origin by
# this very app, so no cross-origin browser request is legitimate by default.
if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
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
    """Liveness + readiness probe.

    The container healthcheck only sees the HTTP status, so an unusable
    database has to surface as 503 instead of a perpetual `{"status": "ok"}`.
    """
    try:
        conn = database.get_connection()
        try:
            conn.execute("SELECT 1").fetchone()
            # Keep the probe inside the healthcheck timeout (5s in compose):
            # a write lock held longer than this is itself a failure.
            conn.execute("PRAGMA busy_timeout = 3000")
            # BEGIN IMMEDIATE acquires the write lock, so a read-only data
            # directory (or unwritable -wal/-shm sidecars) fails here.
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ROLLBACK")
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            schema_version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        raise HTTPException(status_code=503, detail="数据库不可用") from exc
    return {
        "status": "ok",
        "checked_at": clock.now().isoformat(),
        "db": {"journal_mode": journal_mode, "schema_version": schema_version},
    }


@app.get("/api/v1/config")
def get_config():
    return {
        "editable_day_window": config.EDITABLE_DAY_WINDOW,
        "subjects": config.SUBJECTS,
    }


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
