# LeaveTrackerPro — Architecture

Status: **Draft for review — rev 3 (simplified build)** · Date: 2026-11-06
Related: [PRD](PRD.md) · [DESIGN](DESIGN.md) · [SECURITY](SECURITY.md) · [TEST_PLAN](TEST_PLAN.md)

## 1. Goals & Stack
Goals: a public, secure, multi-device web app; portable infrastructure (plain Postgres, S3-compatible
storage, one Docker image); free-tier capable; small enough to build, test and explain end to end.

| Concern | Choice | Why (rejected alternative) |
|---|---|---|
| API | **Python 3.13, FastAPI**, plain `def` routes; **Pydantic v2** (`extra="forbid"`); **pydantic-settings** | Typed models, automatic OpenAPI, dependency injection for auth/DB/clock. Sync routes run in FastAPI's thread pool — enough for this load and simpler than async (rejected: Django — heavier; Flask — no typed validation) |
| Data access | **SQLAlchemy 2.0 (sync `Session`)** + **psycopg 3**; **Alembic** migrations (autogenerate reviewed by hand, `alembic check` in CI) | Mainstream and typed; `alembic upgrade head` runs at container start |
| Tooling | **uv**, **ruff**, **mypy**, **pytest** | Fast, reproducible |
| Database & files | **Supabase Postgres** via a standard `DATABASE_URL`; **Supabase Storage** private bucket via its **S3 API** behind a small `BlobStore` interface | One free project; nothing Supabase-only on the data path; MinIO locally |
| Auth | Backend-owned server-side sessions, **argon2-cffi**, `lt_session` HttpOnly cookie | No tokens in JS, instant revocation (ADR-2) |
| Rate limiting | **slowapi** (in-memory) on **one API instance** | No extra infrastructure; Redis/Upstash is the scale path (ADR-3) |
| Frontend | **React 19 + TypeScript + Vite**, **Tailwind CSS v4** (`@tailwindcss/vite`, `@theme`), React Router, TanStack Query, react-hook-form + zod, lucide-react, native `<dialog>` | Static output for a CDN; typed forms mirror server rules; no component framework to learn |
| Hosting | **Vercel** (SPA + `/api` rewrite) · **Render** (Docker API) · **Supabase** | Same-origin, free tiers, Git-based deploys (ADR-3) |
| CI/CD | GitHub Actions | Lint, type-check, test on real Postgres, build, deploy `main`, smoke |

## 2. Logical Architecture
```
  Phone / tablet / laptop browser
          │  HTTPS (HSTS)                       one origin: https://leavetrackerpro.vercel.app
          ▼
 ┌──────────────────────── Vercel (CDN) ──────────────────────────────┐
 │  /*      → static SPA + security headers from vercel.json           │
 │  /api/*  → rewrite (proxy) to Render ───────────────────────────────┼──┐
 └─────────────────────────────────────────────────────────────────────┘  │ HTTPS
                                                                          ▼
 ┌──────────── Render web service: FastAPI container (1 instance, 1 worker) ───────────┐
 │ middleware: request-id → body-size limit → security headers → Origin check          │
 │   → rate limit (slowapi) → route (session + role dependencies)                      │
 │  api/ (thin routers) → services/ (one DB transaction each) → repositories/          │
 │                          └→ domain/ (pure: workflow, day/streak calculator, policy) │
 │                          └→ adapters/ (BlobStore, file sniffing)                    │
 └──────────────┬────────────────────────────────────────────────┬─────────────────────┘
                │ TLS verify-full · Supavisor session pooler      │ HTTPS · S3 protocol
                ▼                                                 ▼
 ┌──── Supabase Postgres ─────────────────┐       ┌──── Supabase Storage ────┐
 │ schema `leave`, RLS on (no policies),  │       │ private bucket            │
 │ append-only audit_log                  │       │ keys: docs/<uuid4>        │
 └────────────────────────────────────────┘       └───────────────────────────┘
```
Rules: routers hold no business logic; services never touch HTTP objects; `domain/` imports nothing from
FastAPI/SQLAlchemy. The workflow engine is a pure function `transition(request, actor, action, now) ->
TransitionResult | DomainError`, unit-testable without a DB. Clock and blob store are injected.

## 3. Project Layout (monorepo)
```
LeaveTrackerPro-2547237/
├─ README.md                  # live URL, demo accounts, walkthrough, two-minute explanation, local dev
├─ .github/workflows/ci.yml   # lint → type-check → test → build → (main) deploy + smoke
├─ backend/  pyproject.toml, uv.lock, alembic.ini, alembic/versions/
│  ├─ app/  main.py · api/ (deps, errors, routes: auth, leaves, audit, health) · core/ (config,
│  │        security, logging) · domain/ (workflow, calendar, policy, errors) · services/ ·
│  │        repositories/ · models/ · schemas/ · adapters/ (blobstore, sniff) · cli.py (seed,
│  │        create-user, reset-password)
│  └─ tests/  unit/ integration/
├─ frontend/  vite.config.ts, vercel.json, public/ (theme-init.js), src/ (DESIGN §8), e2e/smoke.spec.ts
├─ infra/  Dockerfile, start.sh, docker-compose.yml (postgres:17, minio, api, web)
└─ docs/
```

## 4. Data Model (PostgreSQL, schema `leave`)
Tables live in schema `leave` (not `public`, so Supabase's Data API doesn't expose them). Extension:
`citext`. Status/role values are `text` + `CHECK` (easier to evolve than `ENUM`).

```sql
CREATE TABLE leave.users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext NOT NULL UNIQUE,
  name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 100),
  password_hash text NOT NULL,                       -- argon2id
  role text NOT NULL CHECK (role IN ('EMPLOYEE','MANAGER','HOD')),
  manager_id uuid NULL REFERENCES leave.users(id) CHECK (manager_id IS DISTINCT FROM id),
  is_active boolean NOT NULL DEFAULT true,
  is_demo boolean NOT NULL DEFAULT false,
  failed_logins integer NOT NULL DEFAULT 0,          -- lockout counter (SECURITY §2)
  locked_until timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE leave.sessions (
  id_hash bytea PRIMARY KEY,                         -- sha256(token); raw token never stored
  user_id uuid NOT NULL REFERENCES leave.users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  idle_expires_at timestamptz NOT NULL,
  absolute_expires_at timestamptz NOT NULL
);
CREATE TABLE leave.leave_requests (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,   -- shown as #1234
  employee_id uuid NOT NULL REFERENCES leave.users(id),
  from_date date NOT NULL, to_date date NOT NULL,
  days smallint NOT NULL CHECK (days BETWEEN 1 AND 60),
  streak smallint NOT NULL CHECK (streak >= days),
  leave_type text NOT NULL DEFAULT 'ANNUAL' CHECK (leave_type IN ('ANNUAL','SICK','CASUAL','OTHER')),
  reason text NOT NULL CHECK (char_length(reason) BETWEEN 10 AND 500),
  is_extended boolean NOT NULL,
  status text NOT NULL CHECK (status IN ('PENDING_MANAGER','PENDING_HOD','NEEDS_INFO',
                                         'APPROVED','REJECTED','CANCELLED')),
  resume_status text NULL CHECK (resume_status IN ('PENDING_MANAGER','PENDING_HOD')),
  approver_route text NOT NULL CHECK (approver_route IN ('MANAGER_THEN_HOD','MANAGER_ONLY','HOD_ONLY')),
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (to_date >= from_date),
  CHECK (days = to_date - from_date + 1),
  CHECK ((status = 'NEEDS_INFO') = (resume_status IS NOT NULL)),
  CHECK (is_extended = (streak > 3))
);
CREATE INDEX ON leave.leave_requests (employee_id, from_date, to_date);   -- overlap + chaining
CREATE INDEX ON leave.leave_requests (status, employee_id);
CREATE TABLE leave.leave_decisions (                   -- timeline; never updated
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  request_id bigint NOT NULL REFERENCES leave.leave_requests(id),
  stage text NOT NULL CHECK (stage IN ('MANAGER','HOD','EMPLOYEE')),
  actor_id uuid NOT NULL REFERENCES leave.users(id),
  action text NOT NULL CHECK (action IN ('SUBMIT','APPROVE','REJECT','REQUEST_INFO','RESPOND','CANCEL')),
  from_status text NULL, to_status text NOT NULL,
  comment text NULL CHECK (char_length(comment) <= 1000),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE leave.documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id bigint NOT NULL REFERENCES leave.leave_requests(id),
  uploaded_by uuid NOT NULL REFERENCES leave.users(id),
  original_name text NOT NULL CHECK (char_length(original_name) <= 120),  -- sanitised, display only
  storage_key text NOT NULL UNIQUE,                  -- 'docs/<uuid4>', never from user input
  mime text NOT NULL CHECK (mime IN ('application/pdf','image/png','image/jpeg',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document')),
  size_bytes integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 3145728),     -- 3 MB
  sha256 bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE leave.audit_log (                         -- append-only
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  actor_id uuid NULL, actor_role text NULL,
  action text NOT NULL, entity_type text NOT NULL, entity_id text NULL,
  details jsonb NOT NULL DEFAULT '{}',               -- ids, before/after status; never reason/comment text
  ip inet NULL, request_id text NULL
);
-- plus indexes on every foreign key and audit_log (entity_type, entity_id, id), (actor_id, id)
```

**Append-only audit.** The baseline migration runs `REVOKE UPDATE, DELETE, TRUNCATE ON leave.audit_log
FROM <app DB user>`, so the app can only `INSERT`/`SELECT` audit rows. Backstop: `BEFORE UPDATE OR DELETE`
(row) and `BEFORE TRUNCATE` (statement) triggers raise an exception, so even a role that re-grants itself
the privilege cannot silently rewrite history. A hash chain is a stretch goal (§11).

**Time.** Dates are `date`; timestamps `timestamptz` (UTC). `ORG_TZ` (default `Asia/Kolkata`) decides "today".

### 4.1 Database access & RLS
- The API connects as **one DB user** (the Supabase project's `postgres` user via the session pooler). It
  owns the schema, so Alembic can run at start-up, and as owner it is not subject to RLS — **the API is the
  only data path** and enforces authorisation itself (SECURITY §5).
- **RLS enabled on every table, with no policies** → deny-by-default for every other role (Supabase
  `anon`/`authenticated` via the Data API). Plus `REVOKE ALL ON SCHEMA leave FROM anon, authenticated,
  public`; `leave` is not an exposed Data API schema.
- The Supabase `service_role` and `anon` keys are not used and never reach the browser.

## 5. API (JSON, prefix `/api/v1`)
Same origin as the SPA. Errors use one envelope (§6). All routes need a session except login and health.
Every route declares its role with `Depends(require_role(...))`; a test fails on any route without one
(TEST_PLAN S2). camelCase aliases; the `employeeName/fromDate/toDate/reason` shape is preserved.

| Method & path | Role | Purpose |
|---|---|---|
| POST `/auth/login` | public | `{email, password}` → sets `lt_session`; returns user |
| POST `/auth/logout` | any | Deletes the session, clears the cookie |
| GET `/auth/me` | any | User, role, `isDemo`, `orgToday` (date in `ORG_TZ`), badge counts |
| POST `/auth/password` | any (non-demo) | `{currentPassword, newPassword}`; revokes other sessions |
| POST `/leaves/preview` | EMPLOYEE, MANAGER | `{fromDate, toDate}` → `{days, streak, isExtended, chain[], requiresDocuments, approvalChain}`; writes nothing |
| POST `/leaves` | EMPLOYEE (MANAGER for own) | `application/json` with the mandated body, **or** `multipart/form-data`: part `data` = the same JSON + up to **3** `files` (≤ 3 MB each) |
| GET `/leaves/mine?status=&page=&size=` | any | Own history, newest first (`size` ≤ 50) |
| GET `/leaves/pending?page=&size=` | MANAGER, HOD | Queue awaiting *my* decision, oldest first |
| GET `/leaves/{id}` | owner / assigned or past approver | Detail + timeline + documents |
| POST `/leaves/{id}/decision` | MANAGER, HOD | `{action: APPROVE\|REJECT\|REQUEST_INFO, comment?, version}` |
| POST `/leaves/{id}/respond` | owner, when NEEDS_INFO | JSON `{comment, version}` or multipart (`data` + up to 3 `files`) |
| POST `/leaves/{id}/cancel` | owner, while not final | `{version}` |
| GET `/leaves/{id}/documents/{docId}?disposition=attachment\|inline` | owner / approvers | Streamed download (`inline` only for PDF/PNG/JPEG) |
| GET `/audit?entity=&entityId=&actor=&from=&to=&cursor=` | HOD | Read-only audit view |
| GET `/api/healthz` · `/api/readyz` | public | Liveness (no I/O) · `SELECT 1` + Alembic head matches → 200 `{version}`, else 503 |

- **Why one multipart request?** Files arrive with the leave they belong to: no "uploaded but unattached"
  state, no cleanup job, no extra endpoints. Limits are settings (`MAX_UPLOAD_FILES`, `MAX_UPLOAD_MB`) so
  they can be lowered if the Vercel rewrite's body limit is smaller than ~9 MB (§12).
- **Double submit:** the button is disabled while submitting; a retry of the same dates hits the overlap
  rule, whose message links the existing request.
- **OpenAPI:** `/api/docs` only when `APP_ENV=local`. CI generates the frontend's TypeScript types with
  `openapi-typescript` and fails if the committed types are stale (`git diff --exit-code`).

## 6. Error Model (friendly)
```json
{ "error": { "code": "VALIDATION_FAILED", "message": "Please fix the highlighted fields.",
             "fields": { "toDate": "End date must be on or after the start date." }, "requestId": "01JC…" } }
```
| Code | HTTP | Notes |
|---|---|---|
| VALIDATION_FAILED | 422 | `RequestValidationError` re-mapped to friendly per-field text (no raw Pydantic messages) |
| DOCUMENT_REQUIRED | 422 | extended leave with no documents |
| OVERLAP | 409 | names the conflicting request |
| STALE_VERSION | 409 | optimistic lock |
| INVALID_TRANSITION | 409 | state-machine refusal |
| UNAUTHENTICATED | 401 | no/expired session |
| FORBIDDEN | 403 | role not allowed, Origin check failed, demo password change |
| NOT_FOUND | 404 | also "exists but not yours" (anti-enumeration) |
| PAYLOAD_TOO_LARGE | 413 | body, file size or file count over limit |
| QUOTA_EXCEEDED | 413 | per-user demo storage quota |
| UNSUPPORTED_FILE | 415 | content sniffing failed / not allowed; also a non-JSON/multipart body on mutating routes |
| RATE_LIMITED | 429 | with `Retry-After`; slowapi limits and login lockout |
| SERVICE_UNAVAILABLE | 503 | DB/storage unreachable |
| INTERNAL | 500 | generic text + requestId; details only in logs |

## 7. Key Flows
READ COMMITTED; every service call is one `with session.begin():` block; statement timeout 5 s.

**Submit:** validate (Pydantic, then domain rules) → validate files (count, size while reading, magic
bytes, DOCX checks — SECURITY §7) → `BlobStore.put('docs/<uuid4>')` → **transaction:** `SELECT … FROM
users WHERE id = :me FOR UPDATE` (serialises this employee's submits) → overlap query → load the
employee's nearby active/approved requests and compute `days`, `streak`, `is_extended` with the pure
`calendar.streak()` → extended without files → `DOCUMENT_REQUIRED` → set `approver_route` → INSERT
request, documents, decision(SUBMIT), audit → COMMIT. On failure the blobs just written are deleted.
Two simultaneous submits by one employee therefore run one after the other; the second gets `OVERLAP`.

**Decide:** `SELECT … FROM leave_requests WHERE id = :id FOR UPDATE` → approver relation join (not mine →
`NOT_FOUND`) → `version` check (→ `STALE_VERSION`) → `workflow.transition()` (actor ≠ requester, stage,
route, documents, comment rules) → UPDATE status/`resume_status`, `version = version + 1` → INSERT decision
+ audit → COMMIT. A concurrent second decider waits on the lock, then gets 409.
**Respond:** same lock + version pattern, optional files as in Submit; status returns to `resume_status`.

**Queue query** (authorisation inside the SQL): manager: `status = 'PENDING_MANAGER' AND e.manager_id =
:me`; HOD: `status = 'PENDING_HOD' AND ((approver_route = 'MANAGER_THEN_HOD' AND m.manager_id = :me) OR
(approver_route = 'HOD_ONLY' AND e.manager_id = :me))`. `approver_route` is fixed at submit: standard →
`MANAGER_ONLY`, extended → `MANAGER_THEN_HOD`, manager's own leave → `HOD_ONLY` (starts in `PENDING_HOD`,
PRD §5.3 rule 8).

**Download:** same visibility predicate as `GET /leaves/{id}` → audit `DOC_DOWNLOADED` → stream
`BlobStore.get()` via `StreamingResponse` with DB `Content-Type`, `Content-Disposition`, `nosniff`,
`CSP: sandbox`.

## 8. Configuration (pydantic-settings)
With `APP_ENV=production` the app refuses to boot unless `COOKIE_SECURE=true`, `DATABASE_URL` has
`sslmode=verify-full`, all `ALLOWED_ORIGINS` are `https://`, and `DEMO_PASSWORD` is set when
`DEMO_MODE=true`. API docs are always off in production.

| Variable | Purpose | Local | Prod (where) |
|---|---|---|---|
| `APP_ENV` | `local` / `production` | `.env` | Render env |
| `DATABASE_URL` | Supavisor **session** pooler `:5432`, `sslmode=verify-full&sslrootcert=…` | compose | Render **secret** |
| `DB_POOL_SIZE` | pool size (default 5) | default | Render env |
| `STORAGE_S3_ENDPOINT` / `_REGION` / `STORAGE_BUCKET` | Supabase Storage S3 endpoint, bucket `leave-documents` | MinIO | Render env |
| `STORAGE_S3_ACCESS_KEY_ID` / `STORAGE_S3_SECRET_ACCESS_KEY` | server-side S3 credentials | MinIO | Render **secret** |
| `ALLOWED_ORIGINS` | exact origins for the Origin check (CORS stays off) | `http://localhost:5173` | `https://leavetrackerpro.vercel.app` |
| `COOKIE_SECURE` / `SESSION_IDLE_MIN` / `SESSION_ABSOLUTE_H` | cookie & session policy (30 min / 8 h) | false | true |
| `TRUSTED_PROXY_HOPS` | right-most `X-Forwarded-For` entries that are infrastructure | 0 | measured on day one |
| `ORG_TZ` | "today" for validation | Asia/Kolkata | Asia/Kolkata |
| `DEMO_MODE` / `DEMO_PASSWORD` | enables `seed` + demo quota / seeded password | true / dev | true / Render **secret** |
| `MAX_UPLOAD_FILES` / `MAX_UPLOAD_MB` / `DEMO_QUOTA_MB` | 3 / 3 / 20 | default | default |
| `LOG_LEVEL`, `SENTRY_DSN` (optional) | observability | info | Render |
| Frontend, build-time, **non-secret** | `VITE_DEMO_MODE`, `VITE_DEMO_PASSWORD` (the published demo password), `VITE_APP_VERSION` | `.env.local` | Vercel env |

`.env` is git-ignored; `.env.example` lists keys with dummy values.

## 9. Deployment
### 9.1 Topology: same-origin via Vercel rewrite
Chosen: SPA and `/api/*` on one host; Vercel rewrites `/api/*` to Render. The cookie is first-party and
host-only (`SameSite=Strict`), so Safari's third-party-cookie blocking doesn't matter; no CORS or
preflights; CSP `connect-src 'self'`. Rejected: SPA on `*.vercel.app` + API on `*.onrender.com` with
credentialed CORS — both are Public Suffix List domains, so the API cookie would be third-party. With a
custom domain, `app.`/`api.` subdomains become a viable alternative.

### 9.2 Hosts & environments
- **Vercel:** builds `frontend/` on pushes to `main` (Git integration). `vercel.json`: rewrite
  `/api/:path*` → `https://<render-service>.onrender.com/api/:path*`; SPA fallback to `/index.html`;
  security headers (SECURITY §8.2). Preview deployments off (their origins aren't in `ALLOWED_ORIGINS`
  anyway).
- **Render:** Docker web service, region Singapore, health check `/api/healthz`, **one instance**,
  auto-deploy off (CI calls the deploy hook). Free tier; **Starter (always-on) during the evaluation
  window** (PRD §10 Q9).
- **Supabase:** one project in `ap-southeast-1`, private bucket `leave-documents`.

| Env | Frontend | API | DB / Storage |
|---|---|---|---|
| local | Vite `:5173` with `server.proxy['/api']` → API (same-origin in dev too) | uvicorn `--reload` in compose | `postgres:17`, MinIO; `seed` |
| CI | — | FastAPI `TestClient` | Postgres 17 service container; MinIO via `docker run` |
| production (public demo) | Vercel | Render | Supabase; `seed` |

No staging: PRs are gated by CI; `main` deploys to production, then the post-deploy smoke runs.

### 9.3 Container & start-up
- Multi-stage `python:3.13-slim`: `uv sync --frozen --no-dev` in the builder; runtime copies `.venv`,
  `app/`, `alembic/`, `start.sh` and the Supabase CA; non-root UID 10001.
- `start.sh`: `alembic upgrade head` → if `DEMO_MODE=true`, `python -m app.cli seed` (idempotent) →
  `exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-server-header`. One
  worker keeps the in-memory limiter exact; sync routes still run concurrently in the thread pool.
- Migrating at start is safe with exactly one instance. Migrations stay additive (drop old columns in a
  later release) so the previous image still runs after a rollback.
- DB connection: Supavisor **session mode** `:5432` (IPv4-reachable; the direct host is IPv6 by default);
  `pool_size=5, max_overflow=2, pool_pre_ping=True`; `sslmode=verify-full` with the Supabase CA.

### 9.4 Seeding & demo
`python -m app.cli seed` upserts the demo users (`ON CONFLICT (email) DO UPDATE`) and adds history only
for users who have none, with dates relative to today; it refuses unless `DEMO_MODE=true`. Demo accounts
(`is_demo=true`) cannot change their password and are exempt from lockout. No automatic reset: if the
demo gets messy, the operator clears it from the Supabase SQL editor (README runbook) and the next start
re-seeds.

### 9.5 CI/CD (GitHub Actions, `ci.yml`)
| Job | Trigger | Steps |
|---|---|---|
| backend | PR, push | `uv sync --frozen` → `ruff check` + `ruff format --check` → `mypy app` → `pytest` (Postgres service container, MinIO via `docker run`; includes migration checks) → `pip-audit` (optional `bandit`) |
| frontend | PR, push | `npm ci` → `eslint` → `tsc --noEmit` → OpenAPI types drift check → `vitest run` → `vite build` → bundle secret grep → `npm audit --audit-level=high` |
| security | PR, push | `gitleaks` |
| deploy | push to `main`, after all above | Render deploy hook (`RENDER_DEPLOY_HOOK_URL` secret) → poll `/api/readyz` until `version` = commit SHA → smoke (TEST_PLAN §9) |

Dependabot covers pip, npm and Actions. A failed smoke emails an alert; rollback = previous deploy in the
Render and Vercel dashboards.

### 9.6 Operations
- **Cold start:** free Render instances sleep when idle and take tens of seconds to wake. Mitigations:
  Starter instance during assessment; an uptime monitor (e.g. UptimeRobot, 5 min) on `/api/readyz`, which
  also stops the Supabase free project pausing; the SPA shows "Waking up the server…" after 3 s and
  TanStack Query retries GETs. Keep-warm pings may conflict with free-tier fair use — hence Starter.
- **Backups:** Supabase Free has none; the demo is rebuilt with `alembic upgrade head` + `seed`. Real data
  needs Supabase Pro backups and a copy job for storage objects.
- **Logs:** JSON with `request_id` (also `X-Request-ID`), user id, route, status, latency; never passwords,
  cookies, reasons, comments or file contents. Optional Sentry (`send_default_pii=False`).
- **Cost:** Vercel Hobby, Render Free (Starter ~US$7/mo during assessment), Supabase Free, GitHub Actions
  free minutes. Verify current pricing.

## 10. Decisions (ADR summary)
| # | Decision | Chosen | Why not the alternative | Consequence |
|---|---|---|---|---|
| ADR-1 | Stack | Sync FastAPI + SQLAlchemy 2.0 + Alembic; Supabase Postgres; React + Vite + Tailwind v4 | Async SQLAlchemy: more concepts, no gain at this load. Django: heavier. Next.js: SSR not needed | Simple, typed end to end; thread pool bounds concurrency |
| ADR-2 | Auth | Server-side sessions, argon2id, HttpOnly cookie | Supabase Auth/JWT: token refresh and storage, a second user store to sync with roles, signup/magic-link features to disable | Instant revocation; we own lockout; MFA is an extension |
| ADR-3 | Hosting | Vercel rewrite → one Render container → Supabase, same-origin | Cross-origin CORS (third-party cookies); several instances (need a shared rate-limit store) | One proxy hop; in-memory limiter only valid for one instance |
| ADR-4 | Files | Sent with the leave in one multipart request; private bucket; downloads streamed via the API | Upload-then-attach (extra state + cleanup job); signed URLs (leaked URL works until expiry, headers not ours) | Bodies ≤ ~9 MB; every byte passes authz and our headers |
| ADR-5 | Concurrency | `FOR UPDATE` on the employee row for overlap/streak; request row lock + `version` for decisions | Exclusion constraint (`btree_gist`): harder to explain — future hardening. SERIALIZABLE + retries | Deterministic 409s; relies on all writes going through the service |
| ADR-6 | Audit | Append-only table: app user has INSERT/SELECT only + blocking triggers | Hash chain + advisory lock: tamper-evidence against a DB owner, but a global write lock — stretch goal | Simple and enforced; a DB owner could still disable the trigger |

## 11. Evolution Path & Stretch Goals
- **Scale out:** Redis/Upstash for slowapi → several API instances (sessions are already in Postgres);
  migrations move to a CI release step.
- **DB hardening:** separate least-privilege runtime role + request-scoped RLS policies; GiST exclusion
  constraint on `(employee_id, daterange)` as a DB-level overlap backstop.
- **Tamper-evident audit (stretch):** a `BEFORE INSERT` trigger sets `hash = sha256(prev_hash ‖ record)`
  under a transaction-scoped advisory lock (so chain order is well-defined), plus a verify command that
  reports the first broken row. Detects history rewritten by someone with DB-owner access, at the cost of
  serialising all audit writes.
- **Files:** signed download URLs (≤ 60 s, issued after authz); ClamAV scanning; client-side photo
  downscaling.
- **Features:** email notifications, working-day calendar, balances, SSO (OIDC), MFA (TOTP), user admin UI.

## 12. Delivery Plan
0. **Walking skeleton, deployed on day 1:** health endpoints, Alembic baseline (schema, RLS, audit
   trigger), React shell with tokens, Vercel ↔ Render ↔ Supabase wired, CI + deploy + smoke.
   **Day-one verification list** (record results in the README):
   1. Max body through the Vercel → Render rewrite (need ~9 MB); else lower `MAX_UPLOAD_FILES`/`MAX_UPLOAD_MB`.
   2. Vercel rewrite timeout vs Render free-tier wake time; else rely on Starter.
   3. `Set-Cookie` through the rewrite is stored for the Vercel host on iOS Safari.
   4. `Origin` reaches the API unchanged through the rewrite (the Origin check depends on it).
   5. `X-Forwarded-For` shape at the API → `TRUSTED_PROXY_HOPS`.
   6. Session pooler works with `sslmode=verify-full` and the Supabase CA.
   7. The Supabase `postgres` user is not a superuser, so the audit `REVOKE` applies (the trigger backs it up either way).
   8. A commit SHA (e.g. `RENDER_GIT_COMMIT`) is available at runtime for `/api/readyz`.
1. Domain: workflow, day/streak calculator, validators + unit tests (U*, W*).
2. Auth: login/logout/me/password, sessions, Origin check, lockout, rate limits, headers.
3. Leaves: submit with files, preview/list/detail, decision/respond/cancel, audit (I*).
4. Frontend screens (DESIGN §4), responsive + dark mode.
5. Hardening: IDOR matrix, upload abuse corpus, Lighthouse/axe.
6. Demo: seed, banner, quota, uptime monitor, README.
7. Release: SECURITY §16 checklist, cross-device UAT, tag `v1.0.0`.
