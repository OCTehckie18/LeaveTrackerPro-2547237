# LeaveTrackerPro — Backend (FastAPI)

Status: **Part 1 of 7** — foundation, database schema, business rules. No login or leave endpoints yet.

## Prerequisites
Python 3.13 (uv installs it for you), [uv](https://docs.astral.sh/uv/), Docker Desktop.

## Run it locally
```bash
# 1. from the repo root: start Postgres 17 (host port 5433, creates leavetracker + leavetracker_test)
docker compose -f infra/docker-compose.yml up -d

# 2. from backend/
cd backend
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
uv sync                         # installs dependencies into .venv
uv run alembic upgrade head     # creates schema "leave" and all tables
uv run uvicorn app.main:app --reload --port 8000
```
Then open http://127.0.0.1:8000/api/healthz, `/api/readyz` and `/api/docs` (docs exist only when `APP_ENV=local`).

> Use `127.0.0.1`, not `localhost`: on Windows `localhost` tries IPv6 first and each connection stalls ~8 s.

## Checks
```bash
uv run pytest -q                                    # 62 tests, no database needed
TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/leavetracker_test uv run pytest -q
                                                    # + 17 migration tests on real Postgres
uv run ruff check . && uv run ruff format --check . # lint + format
uv run mypy app tests                               # strict type check
```
PowerShell: `$env:TEST_DATABASE_URL = "postgresql://..."` then `uv run pytest -q`.
The migration tests **drop and recreate schema `leave`** in the database they are given.

## What exists (Part 1)
| Area | Where |
|---|---|
| Config + production safety guards | `app/core/config.py` |
| Tables, constraints, RLS, append-only audit | `app/models/`, `alembic/versions/0001_baseline.py` |
| Day / streak rule (> 3 consecutive days, chaining) | `app/domain/calendar.py` |
| Field validation + friendly messages | `app/domain/validation.py` |
| Approval state machine (Manager → HOD, info loop) | `app/domain/workflow.py` |
| Friendly error envelope, request-id, security headers | `app/api/errors.py`, `app/api/middleware.py` |
| Health / readiness | `app/api/routes/health.py` |
