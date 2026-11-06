# LeaveTrackerPro

Employees submit leave; Managers approve or reject it. Leave of **more than 3 consecutive days** is
*extended leave*: it needs supporting documents and **two approvals — Manager, then HOD**.

Stack: Python (FastAPI) · PostgreSQL (Supabase-ready) · React + Vite + Tailwind CSS v4.
Design docs: [`docs/`](docs/) (PRD, ARCHITECTURE, DESIGN, SECURITY, TEST_PLAN).

## Run it (one command)
Requires Docker Desktop.
```bash
docker compose up --build
```
Open **http://localhost:8080**. The first start builds the images, creates the database, applies the
migration and loads demo data. Stop with `Ctrl+C`; `docker compose down -v` also wipes the data.

### Demo accounts (password for all: `DemoPass#2026`, demo only)
| Email | Role | Notes |
|---|---|---|
| john@acme.test, jane@acme.test | Employee | report to Meera |
| manager@acme.test (Meera) | Manager | first approver for John and Jane |
| hod@acme.test (Harish) | HOD | second approver; the only one who can open the audit log |
| priya@acme.test, raj@acme.test | Manager, Employee | a second team, to see that people can't see each other's requests |

## Try the main flow (about 3 minutes)
1. Sign in as **John** → *Apply for leave*. Pick 3 days: no warning. Pick 5 days: the orange
   *Extended leave* box appears and Submit stays disabled until you attach a PDF/PNG/JPG.
2. Sign in as **Meera** → *Approvals* → open John's request → view the document → **Approve**.
   It now shows *Awaiting HOD* (step 1 of 2) and leaves Meera's queue.
3. Sign in as **Harish** → *Approvals* → **Ask for info** → John sees a blue banner and replies.
4. Harish approves → *Approved*. Open **Audit log** to see every step.
5. Try **Reject** (a comment is required) and **Cancel** on a pending request.

Seeded data already shows every status colour: Pending, Awaiting HOD, Info needed, Approved, Rejected.

## Develop with hot reload
```bash
docker compose up -d db api                  # Postgres (host :5433) + API (host :8001), demo data seeded
cd frontend && cp .env.example .env.local && npm install
npm run dev                                  # UI on http://localhost:5173, /api is proxied to :8001
```
Or run the API outside Docker: `cd backend && cp .env.example .env && uv sync && uv run alembic upgrade head`,
then `DEMO_MODE=true DEMO_PASSWORD='DemoPass#2026' uv run python -m app.cli seed` and
`uv run uvicorn app.main:app --reload` (port 8000; start Vite with `API_PROXY=http://127.0.0.1:8000`).

## Tests
```bash
cd backend
uv run pytest -q                                   # unit + API tests (no database)
TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/leavetracker_test uv run pytest -q
uv run ruff check . && uv run mypy app tests       # lint + strict types
cd ../frontend && npm run build                    # type-check + production build
```
PowerShell: set `$env:TEST_DATABASE_URL = "..."` first. Use `127.0.0.1`, not `localhost` (Windows IPv6 stall).

## Deploying (public link)
Vercel (frontend, `frontend/vercel.json` rewrites `/api` to the API) + Render (Docker image from
`infra/Dockerfile.api`) + Supabase (Postgres + Storage). Required settings are listed in
`docs/ARCHITECTURE.md` §8–9 and `backend/.env.example`. Set `APP_ENV=production`; the app then refuses to
start unless cookies are `Secure`, the DB uses `sslmode=verify-full` and origins are `https://`.

## How AI tools were used
Claude Code planned the architecture and docs, then generated the code in reviewed slices; every business
rule is covered by tests (`backend/tests`) so changes could be checked rather than trusted.
