# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run dev server (port 15000)
PYTHONPATH=backend uv run uvicorn backend.main:app --host 0.0.0.0 --port 15000

# Run with Docker
docker compose up -d
```

## Architecture

FastAPI + SQLite backend serving a single-file HTML frontend (no JS framework). All API routes prefixed with `/api/v1`.

**Backend** (`backend/`):
- `main.py` — FastAPI app, registers routers, mounts frontend as static files
- `config.py` — Port (15000), DB path, cookie TTL, editable day window (3 days for child)
- `database.py` — SQLite connection via context manager; auto-creates tables and seeds 15 tasks + 2 users on first run
- `auth.py` — Session-based auth (cookie), role checking (`require_parent`, `require_child`, `require_any`)
- `routers/` — `auth_router.py`, `tasks.py`, `records.py`, `summary.py`

**Frontend** (`frontend/index.html`): Single-file SPA (~33KB) with inline CSS/JS.

**Data** (`data/habits.db`): SQLite, gitignored, auto-created.

## Key Conventions

- **`PYTHONPATH=backend` is mandatory** — code uses bare imports (`import database`, `import config`), not relative/package imports
- All API routes under `/api/v1`
- Auth uses session cookies, not JWT
- Child role: can only edit records for the last 3 days; parent: no restriction
- Weekly summary uses ISO week numbers
- Dates: API uses `YYYY-MM-DD`, display uses `MM/DD`
- Timezone: `Asia/Shanghai`
- Reward logic: task is "qualifying" only if weekly completions ≥ `weekly_min`; qualifying tasks earn `reward × actual_count`

## Roles

| Role | Username | Password |
|------|----------|----------|
| Parent (admin) | tayhe | parents |
| Child | meow | child |

## Key Files

- `AGENT.md` — Full project spec and data model (reference for business rules)
- `HISTORY.md` — Changelog from v2.0 to v3.0
