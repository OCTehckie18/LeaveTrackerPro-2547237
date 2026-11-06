# LeaveTrackerPro — Product Requirements (PRD)

Status: **Draft for review — rev 3 (simplified build)** · Date: 2026-11-06
Related: [ARCHITECTURE](ARCHITECTURE.md) · [DESIGN](DESIGN.md) · [SECURITY](SECURITY.md) · [TEST_PLAN](TEST_PLAN.md)

> Rev 3: same features and business rules as rev 2 with a smaller implementation. Stack: **Python
> (FastAPI) + Supabase Postgres & Storage + React/Vite/Tailwind v4**, hosted on Vercel + Render + Supabase.

## 1. Purpose
A simple, secure portal where employees submit leave requests and managers approve or reject them.
Leave longer than 3 consecutive days is "extended leave": it requires supporting documents and a
two-step approval (Manager, then HOD).

**Deliverable**
1. A **deployed public URL** (HTTPS) that works on phones, tablets and laptops, pre-loaded with demo data.
2. A **README** in the repo root that gives, in this order: the live URL, the demo accounts (clearly
   labelled *demo-only*), a 5-minute guided walkthrough, the two-minute explanation (§1.1), then local
   development (`docker compose up`), test commands and the deployment runbook.
3. The source monorepo (`/backend`, `/frontend`, `/infra`, `/docs`) with CI green.

**Skills the submission demonstrates (assessment criteria):** workflow (state machine, two-step
approval), form validation (zod mirror + Pydantic authority), CRUD (REST API under `/api/v1`), code/system
knowledge (these docs, ADRs, tests), and **AI tool usage** — the README includes a short "How AI was used"
section: which AI assistants were used for planning, scaffolding, test generation and review; how output
was verified (tests, type checks, security scans, manual review); and what was deliberately not delegated
(security decisions, final review). No AI/LLM feature ships in the product itself (out of scope).

### 1.1 Two-minute explanation (README-ready)
**What it is.** LeaveTrackerPro is a web app where employees apply for leave and their managers approve
or reject it. It runs at a public HTTPS link and works on a phone, tablet or laptop.

**Three roles.** *Employees* apply, attach documents, answer questions and cancel pending requests.
*Managers* approve, reject or ask for more information on their direct reports' requests. *HODs* (the
managers' manager) give the second approval for extended leave and can read the audit log.

**The >3-day rule.** Leave counts calendar days, inclusive. If a request — or a chain of back-to-back
requests — is longer than 3 days, it is *extended*: the employee must attach a document, and it needs the
manager's approval **and then** the HOD's. Exactly 3 days is not extended. Chaining stops people splitting
9 days into three 3-day requests.

**Architecture in five bullets.**
- React + TypeScript SPA (Vite, Tailwind v4) served from Vercel's CDN.
- Vercel forwards `/api/*` to a FastAPI container on Render, so browser and API share one origin (no CORS).
- The API is layered: thin routes → services (one DB transaction each) → a pure, unit-tested workflow
  state machine and day/streak calculator.
- Data in Supabase Postgres (schema managed by Alembic); documents in a private Supabase Storage bucket,
  streamed through the API only after an authorisation check.
- GitHub Actions lints, type-checks, tests against a real Postgres, builds, deploys `main` and runs a
  post-deploy smoke test.

**Three security highlights.**
1. Server-side sessions in an HttpOnly, Secure, SameSite=Strict cookie (no tokens in JavaScript), argon2id
   password hashes, login lockout and rate limits.
2. Authorisation is checked on every request inside the SQL query itself: you only ever see your own
   requests or your team's; anything else returns 404. Nobody can approve their own leave or skip the HOD.
3. Uploads are checked by content (magic bytes), stored under random names in a private bucket, and
   downloaded only as attachments with `nosniff`; every important action lands in an append-only audit log.

**How AI tools were used.** AI assistants helped draft these planning documents, scaffold code and
tests, and review for edge cases; every output was checked by tests, type checks, security scans and my
own review. Security decisions and the final review were not delegated.

### 1.2 Tech choices mapped to my experience
| Area | Choice | My experience | What's new to learn |
|---|---|---|---|
| API | Python + FastAPI (sync routes) | Python/FastAPI | — |
| ORM & migrations | SQLAlchemy 2.0 + Alembic | SQLite in a prior project | Postgres row locks (`FOR UPDATE`), Alembic autogenerate review |
| Database & storage | Supabase Postgres + Storage | Supabase Postgres | Storage via its S3 API, pooler connection string |
| Frontend | React + TS + Vite | React/TS/Vite | Tailwind v4 `@theme`, TanStack Query, react-hook-form + zod |
| Auth & access | Server-side sessions, roles | RBAC | argon2 hashing, cookie flags, Origin check |
| Hosting | Vercel + Render (Docker) | Vercel, Docker | Render web service + deploy hook |
| CI/CD | GitHub Actions | GitHub Actions | Postgres service container, post-deploy smoke |

## 2. Personas / Roles
| Role | Description | Key abilities |
|---|---|---|
| EMPLOYEE | Regular staff | Apply, view own history/status, attach documents, answer info requests, cancel own pending request |
| MANAGER | Direct manager of employees | View pending queue, view documents, approve, reject, comment, ask for more info |
| HOD | Head of Department; manager's manager | Everything a manager can do, for the 2nd approval step of extended leave; read-only audit log view |

Hierarchy: `Employee.manager_id → Manager`, `Manager.manager_id → HOD`. A user can only act on
requests of their direct reports (HOD: on requests routed to them). Users are seeded by an
administrator; **self-signup is disabled** (no registration endpoint exists).

## 3. Scope
### In scope (MUST)
- Login with role-based access (email + password, server-side session cookie).
- Employee: apply for leave, list own requests, see status + decision comments + timeline, attach documents, respond to "more info" requests, cancel a pending request.
- Manager: pending queue, request detail, document viewing, approve / reject (with comments), ask for more info.
- Extended-leave rule (> 3 consecutive days): mandatory documents + Manager approval **and** HOD approval.
- Form validation (client-side for speed, server-side authoritative), friendly error messages.
- Append-only audit log of all important events.
- Colour-coded statuses, responsive UI (360 px phone → 1440 px+ desktop), works on touch devices.
- Public HTTPS deployment + README with URL, demo credentials and walkthrough.
- Change own password (`POST /auth/password`) for non-demo accounts.

### Plus points (SHOULD — all planned)
Audit logs · friendly errors · colour coding · responsive UI · dark mode.

### Out of scope (explicit non-goals)
Leave balances/accruals, public-holiday calendars, email/SMS/push notifications (in-app only),
SSO/LDAP, MFA, self-signup and user-management UI (users are seeded via CLI), payroll integration,
multi-tenant, cancelling APPROVED leave, native mobile apps, installable/offline PWA. Extension points are
listed in ARCHITECTURE §11.

## 4. Leave Request Data
Mandated input shape (API contract preserved):
```json
{ "employeeName": "John", "fromDate": "2026-11-01", "toDate": "2026-11-05", "reason": "Vacation" }
```
Additional optional field: `leaveType` (ANNUAL, SICK, CASUAL, OTHER; default ANNUAL). Without documents
the body is sent as plain JSON; with documents the **same JSON** travels as the `data` part of a
`multipart/form-data` request alongside up to 3 files (ARCHITECTURE §5).
`employeeName` is accepted for compatibility but the **authenticated identity is authoritative**:
if supplied and it doesn't match the logged-in employee → friendly 422 error (and an audit event);
if omitted it's filled in.

Derived/system fields: `id`, `employeeId`, `days`, `isExtended`, `streak`, `status`, `currentStage`,
`version`, `createdAt`, `updatedAt`, `decisions[]`, `documents[]`. Responses always echo
`employeeName`, `fromDate`, `toDate`, `reason` in the same shape.

## 5. Business Rules
### 5.1 Consecutive-day calculation (strict)
- `days = toDate − fromDate + 1` (inclusive, **calendar days**, weekends/holidays count — the strictest reading of "consecutive").
- **Chaining rule (anti-splitting):** a request is merged with the employee's other *active-or-approved*
  requests (PENDING_MANAGER, PENDING_HOD, NEEDS_INFO, APPROVED) that are contiguous with it (one ends
  the day before another begins). The streak length is the total of the merged chain. If the chain > 3
  → extended. Prevents bypassing the rule via 3 + 3 + 3 day requests.
- `isExtended = streak > 3`. Exactly 3 days is **not** extended.
- Streak is calculated on submit; existing standard requests are not retroactively changed when a
  neighbour is later created (documented limitation) — the new request carries the extended flag.
- "Today" for the past-date check is evaluated in the configured org time zone (`ORG_TZ`, default
  `Asia/Kolkata`), not the server's or the browser's clock.

### 5.2 Validation rules
| Field | Rule | Friendly message |
|---|---|---|
| fromDate / toDate | ISO `YYYY-MM-DD`, real calendar date | "Please pick a valid start date." |
| fromDate | not in the past (today allowed, org TZ) | "Start date can't be in the past." |
| toDate | ≥ fromDate | "End date must be on or after the start date." |
| Range | ≤ 60 days, within next 12 months | "Leave can't exceed 60 days in one request." |
| Overlap | no overlap with own PENDING_MANAGER/PENDING_HOD/NEEDS_INFO/APPROVED request | "You already have leave from {a} to {b} (#{id})." |
| reason | 10–500 chars after trim, no control chars (except newline) | "Please describe the reason (10–500 characters)." |
| leaveType | enum | "Choose a leave type." |
| Documents | required if extended; ≤ 3 files per submission or reply, ≤ 3 MB each; PDF/PNG/JPG/DOCX (verified by content, not extension) | "Leave over 3 days needs at least one supporting document (e.g. medical certificate)." |
| Decision comment | required for REJECT and REQUEST_INFO (≥5 chars); optional for APPROVE; ≤1000 chars | "Please tell the employee why." |
| Password (change) | ≥ 12 chars, ≤ 128, not in the bundled common/breached-password list, ≠ email | "Choose a longer password that isn't commonly used." |

### 5.3 Workflow (state machine)
States: `PENDING_MANAGER`, `PENDING_HOD`, `NEEDS_INFO`, `APPROVED`, `REJECTED`, `CANCELLED`.

```
              submit
                │
   standard ────┴──── extended (docs mandatory)
      │                     │
PENDING_MANAGER ◄───────────┘ (both start here)
  │ approve (standard)           │ approve (extended)
  ▼                              ▼
APPROVED                    PENDING_HOD ── approve ──► APPROVED
  ▲                              │ reject
  │                              ▼
  │    reject (any stage)──► REJECTED
  │
  │   request-info (any stage) ──► NEEDS_INFO ──employee responds──► back to the stage that asked
  employee cancel (own, before final) ──► CANCELLED
```
Rules:
1. Manager may only decide `PENDING_MANAGER` requests of direct reports; HOD only `PENDING_HOD` requests of their department. **Self-approval is impossible** (actor ≠ requester enforced).
2. Extended leave: manager approval moves to `PENDING_HOD` (not final); final approval only by HOD.
3. REJECT at any stage is final; the comment is shown to the employee.
4. REQUEST_INFO records the question and sets `NEEDS_INFO`; employee reply (text and/or new documents) returns the request to the stage that asked.
5. Extended request can't be approved by manager if it has zero documents (defence in depth).
6. Employee can cancel while status is PENDING_MANAGER / PENDING_HOD / NEEDS_INFO. APPROVED cancel is out of scope.
7. All transitions are atomic (one Postgres transaction with a row lock), guarded by optimistic-lock `version`; a stale decision gets "This request was just updated by someone else. Please refresh."
8. A manager's own leave is routed to their HOD (standard: HOD is the single, final approver; extended: HOD is the single approver and documents are still mandatory).

## 6. User Stories & Acceptance Criteria
**Employee**
- E1 Apply: given valid input, the request is created as PENDING_MANAGER; I see it in my list with an amber "Pending" badge and a confirmation toast.
- E2 Extended: when my dates span > 3 days (or chain to > 3) the form immediately shows "Extended leave: documents required, needs Manager + HOD approval" and blocks submit until a document is attached.
- E3 History: I see my requests newest-first, filterable by status, paginated, with status colour + stage ("Awaiting HOD").
- E4 Status detail: timeline of every step with actor, time and comments.
- E5 Respond to info request: banner shows the question; I add reply/documents and resubmit.
- E6 Cancel pending request.
- E7 Multi-device: I can submit on my phone (including attaching a photo of a certificate from the camera roll) and see the same request on my laptop.

**Manager / HOD**
- M1 Pending queue: only requests awaiting *my* decision, oldest first, with employee, dates, days, extended badge.
- M2 Detail: reason, history of the employee's recent leave, documents (preview/download), prior comments.
- M3 Approve (optional comment); M4 Reject (mandatory comment); M5 Ask for more info (mandatory question).
- M6 Extended request shows "Step 1 of 2" / "Step 2 of 2 (HOD)" progress.
- H1 HOD can view the audit log (filter by entity/actor/date).

**Assessor / visitor**
- V1 Opening the public URL on any device shows the login page over HTTPS with a visible "Demo environment" banner listing the demo accounts.
- V2 Following the README walkthrough end-to-end (standard + extended + info loop + reject + audit) succeeds without local setup.

## 7. Non-Functional Requirements
| Area | Target |
|---|---|
| Delivery | Public HTTPS URL; static SPA on Vercel's CDN, one API container on Render, Supabase Postgres + Storage (ARCHITECTURE §9) |
| Availability | Free tiers, no vendor SLA: best effort, uptime monitor every 5 min. If the API is asleep the UI shows "Waking up the server…" after 3 s; an always-on Starter instance during assessment avoids this |
| Performance | Modest, checked manually: list/detail/queue < 500 ms when warm; login page LCP < 3 s on Lighthouse mobile |
| Devices & browsers | Phones 360–430 px, tablets 768–1024 px, laptops 1280–1440 px+; touch and keyboard. Last 2 versions of Chrome, Edge, Firefox; Safari / iOS Safari **16.4+** (Tailwind v4 baseline) |
| Scalability | v1 = **one API instance** (in-memory rate limiter). Scale path: Redis/Upstash limiter → several instances; sessions already in Postgres |
| Security | SECURITY.md (OWASP Top 10, internet-facing threat model) |
| Accessibility | WCAG 2.1 AA: colour never the only signal, keyboard operable, labelled inputs, 44 px touch targets |
| Reliability & ops | Transactional writes, `/api/healthz` + `/api/readyz`, Alembic migrations at container start, JSON logs with request id, audit log separate from app logs |
| Portability & cost | Plain Postgres via `DATABASE_URL`, S3-compatible storage, one Docker image; free tiers (~US$7/month recommended during evaluation for an always-on API) |

## 8. Demo Data & Environment
The public link is a **demo environment**: production configuration (`APP_ENV=production`) with
`DEMO_MODE=true` (seeding + upload quota on the API) and `VITE_DEMO_MODE=true` (banner in the SPA).

| User | Role | Reports to | Notes |
|---|---|---|---|
| hod@acme.test | HOD | — | audit log access |
| manager@acme.test | MANAGER | HOD | |
| john@acme.test, jane@acme.test | EMPLOYEE | Manager | |
| priya@acme.test | MANAGER | HOD | second team, for IDOR demos ("other manager") |
| raj@acme.test | EMPLOYEE | Priya | |

- The shared demo password is **published in the README and on the login banner, labelled "demo only"**.
  The API gets it from the `DEMO_PASSWORD` secret (never hard-coded) for the idempotent
  `python -m app.cli seed` command; the SPA shows it from `VITE_DEMO_PASSWORD` (public by design).
- Demo accounts cannot change their password and are exempt from account lockout (prevents hijacking and
  lockout griefing); per-IP rate limits still apply.
- Seeded history: a mix of APPROVED, REJECTED, NEEDS_INFO, PENDING_HOD and PENDING_MANAGER requests
  (dates relative to "today") so every colour and screen is visible immediately.
- Banner: "Shared demo — don't enter real personal or medical information. Data may be reset."
- Per-user upload quota (20 MB) in demo mode (SECURITY §15).

## 9. Acceptance Criteria for the Deployed Link
1. `https://` with a valid certificate; HTTP redirects to HTTPS; HSTS present.
2. Login page LCP < 3 s on Lighthouse mobile; Lighthouse Accessibility ≥ 90.
3. All screens usable without horizontal scroll at 360, 768 and 1280 px.
4. UAT script (TEST_PLAN §4) passes on an iPhone or Android phone, a tablet, and desktop Chrome/Edge/Firefox.
5. README shows the live URL, demo credentials, walkthrough, two-minute explanation and local-dev steps;
   a new reader reaches "HOD approves extended leave" within 5 minutes.
6. Post-deploy smoke test (TEST_PLAN §9) green; response headers include CSP, HSTS, nosniff,
   `X-Frame-Options`, Referrer-Policy.
7. No secret (DB password, storage keys) appears in the repo, the JS bundle, or HTTP responses.

## 10. Open Questions (defaults chosen — confirm or change)
1. "Consecutive leaves > 3" → **calendar days, inclusive**, with chaining. (Alt: working days only.)
2. Notifications → in-app only (badge/"needs your action", polled every 60 s); email is a documented extension.
3. Manager's own leave → routed to HOD (HOD final). **HOD's own leave → not supported in v1** (no approver above HOD; the Apply page explains this). Alt: route to a designated peer HOD.
4. Backend → **Python 3.13, FastAPI + Pydantic v2 + SQLAlchemy 2.0 (sync, psycopg 3) + Alembic**, deps via **uv**.
5. Auth → **backend-owned** (argon2id + server-side sessions + HttpOnly `lt_session` cookie); Supabase Auth not used (ARCHITECTURE ADR-2). MFA is a documented extension.
6. Topology → **same-origin**: SPA on **Vercel**, `/api/*` rewritten to **one** API container on **Render**; no CORS. Alt API hosts for the same image: Google Cloud Run, AWS.
7. Region → Supabase `ap-southeast-1` (Singapore) and Render Singapore. Alt: Mumbai if the API host offers it.
8. Uploads → sent with the leave (or reply) in one request, **≤ 3 files × 3 MB**. Large phone photos get a friendly "too large — try a smaller photo or a PDF"; client-side downscaling is an extension. Confirm these limits.
9. Evaluation window → upgrade Render to an always-on instance (~US$7/mo) to remove cold starts? Default: **yes, during assessment only**.
10. Rate limiting → in-memory, valid only for one API instance (accepted for the demo; Redis/Upstash when scaling).
11. Custom domain → none by default (`*.vercel.app`). Confirm if one is available.
12. Roles beyond the three (HR/Admin) → not included.
13. Leave ID format → sequential integer shown as `#1234` (authorisation, not secrecy, protects it).
