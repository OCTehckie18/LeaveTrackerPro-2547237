# LeaveTrackerPro — Test Plan

Status: **Draft for review — rev 3 (pytest · Vitest · one Playwright smoke)** · Date: 2026-11-06
Related: [PRD](PRD.md) · [ARCHITECTURE](ARCHITECTURE.md) · [DESIGN](DESIGN.md) · [SECURITY](SECURITY.md)

## 1. Strategy
| Layer | Tooling | Scope | Gate |
|---|---|---|---|
| Backend unit | **pytest**, fake `Clock` | workflow, day/streak calculator, validators, policy, sniffing, error mapper | ≥ 90 % lines on `app/domain` |
| Backend integration | pytest + FastAPI **`TestClient`** + **real Postgres 17** (compose `db` locally, service container in CI); in-memory `BlobStore` fake | every endpoint and error code; authz/IDOR matrix | all green |
| Migrations & storage | Alembic API; MinIO | upgrade on empty DB, drift, constraints, audit trigger; S3 adapter | all green |
| Frontend | **Vitest** + Testing Library + MSW + `vitest-axe` | key components, API client, sanitisers, contrast | all green |
| E2E | **Playwright**: one smoke spec at **360 px and 1280 px** (Chromium) | login → dashboard on the live URL | post-deploy |
| Security in CI | pip-audit, npm audit, gitleaks (optional bandit) | dependencies, secrets | no unaccepted High |
| Manual | UAT, real devices, Lighthouse | cross-device, performance sanity | before release |

Commands: `docker compose up -d db minio` then `uv run pytest`; `npm test`; `npx playwright test`
(`BASE_URL` selects the target). No `datetime.now()` in logic — the `Clock` dependency is overridden.

**Test database:** `alembic upgrade head` once per session. Each test runs in a transaction rolled back at
the end (`join_transaction_mode="create_savepoint"`). Concurrency tests commit for real; a fixture then
truncates with `SET session_replication_role = replica` (skips the audit triggers; test superuser only).

## 2. Unit Tests
### 2.1 Day & streak calculator
| # | Input | Expected |
|---|---|---|
| U1 | 11-01 → 11-01 | 1 day, standard |
| U2 | 11-01 → 11-03 | 3 days, **standard** (boundary) |
| U3 | 11-01 → 11-04 | 4 days, **extended** (boundary) |
| U4 | 11-01 → 11-05 | 5 days, extended |
| U5 | span across weekend / month end / leap day (2028-02-28→03-01) | counts calendar days correctly |
| U6 | existing approved 10-30→10-31 + new 11-01→11-02 | streak 4 → extended (chaining) |
| U7 | existing 10-28→10-29 + new 11-01 | gap day → not chained |
| U8 | chain of three 2-day requests back-to-back | final one extended; streak 6 |
| U9 | adjacent REJECTED/CANCELLED request | ignored in chain |
| U10 | toDate < fromDate; `2026-02-30`; `2026/11/01`; `1730419200` (unix ts); empty | validation errors (no lax coercion) |
| U11 | range 61 days; > 12 months ahead; past date in `Asia/Kolkata` at the 23:30 UTC boundary | validation errors; "today" uses org TZ |

### 2.2 Workflow engine (`transition()`)
| # | State / actor / action | Expected |
|---|---|---|
| W1 | PENDING_MANAGER standard, Manager APPROVE | APPROVED |
| W2 | PENDING_MANAGER extended, Manager APPROVE | PENDING_HOD (not final) |
| W3 | PENDING_HOD, HOD APPROVE | APPROVED |
| W4 | PENDING_HOD, Manager APPROVE | INVALID_TRANSITION |
| W5 | PENDING_MANAGER, HOD APPROVE | INVALID_TRANSITION (no skipping) |
| W6 | any pending, REJECT with comment | REJECTED; without comment → VALIDATION_FAILED |
| W7 | REQUEST_INFO at MANAGER → NEEDS_INFO(resume=PENDING_MANAGER); employee RESPOND → PENDING_MANAGER | round trip |
| W8 | REQUEST_INFO at HOD → respond → PENDING_HOD (not restarted from manager) | stage preserved |
| W9 | actor == requester | FORBIDDEN (self-approval) |
| W10 | manager of another team | NOT_FOUND (policy) |
| W11 | extended, 0 documents, Manager APPROVE | DOCUMENT_REQUIRED |
| W12 | terminal state (APPROVED/REJECTED/CANCELLED) any action | INVALID_TRANSITION |
| W13 | stale `version` | STALE_VERSION |
| W14 | employee cancel in each open state / in final state | ok / INVALID_TRANSITION |
| W15 | respond when not NEEDS_INFO | INVALID_TRANSITION |
| W16 | manager's own leave (route HOD_ONLY): starts PENDING_HOD; HOD APPROVE → APPROVED; manager cannot act on it | per PRD §5.3 rule 8 |

W1–W16 are one parametrised table test. (Stretch: a Hypothesis property test asserting random action
sequences never reach `is_extended ∧ APPROVED` without an HOD approval.)

### 2.3 Other backend units
Validators (reason length, control chars), file sniffing (magic bytes vs extension mismatch, DOCX
structure, macro and zip-bomb rejection), filename sanitiser, password policy (length, common list,
email-derived), argon2 hash/verify, session token hashing, Origin/`Sec-Fetch-Site` check, client-IP
extraction from `X-Forwarded-For` with N trusted hops, error mapper (domain error → code/status/friendly
text; Pydantic error → friendly field text), production settings guard.

### 2.4 Frontend (Vitest + Testing Library + MSW)
| # | Test | Expected |
|---|---|---|
| FE1 | `StatusBadge` for every status | icon + text label + token class; exhaustive over the API union |
| FE2 | Apply form: dates spanning 4 days (MSW preview); 4th file; 4 MB file | extended callout; submit disabled with helper text until a file is chosen; friendly client-side file errors |
| FE3 | Server 422 with `fields` | errors shown on the matching inputs, summary focused |
| FE4 | `apiFetch`: `credentials: 'same-origin'`, JSON vs `FormData` bodies, envelope → `ApiError`, 401 → redirect to `/login?next=…` | pass |
| FE5 | Decision 409 STALE_VERSION | banner shown, typed comment kept |
| FE6 | `next` sanitiser (`//evil.com`, `https://evil`, `/requests/5`) | only same-origin relative accepted |
| FE7 | Token contrast over the `app.css` values | every fg/bg pair ≥ 4.5:1 |
| FE8 | axe (`vitest-axe`) on Apply, Detail and Decision pages, light + dark | no violations |
| FE9 | Cold-start notice when `/api/healthz` > 3 s (fake timers) | "Waking up the server…" shown, then cleared |

## 3. Integration / API Tests (pytest + TestClient, real Postgres)
| # | Scenario | Expected |
|---|---|---|
| I1 | Login ok / bad password / unknown user | 200 + `lt_session` cookie / 401 with identical body |
| I2 | Employee `POST /leaves` JSON, 3 days | 201, PENDING_MANAGER, isExtended=false, response echoes `employeeName/fromDate/toDate/reason` |
| I3 | 4 days, no files | 422 DOCUMENT_REQUIRED, friendly text |
| I4 | 4 days, multipart `data` + valid PDF | 201, isExtended=true, document listed, blob stored under `docs/<uuid>` |
| I5 | `employeeName` ≠ session user | 422 + audit VALIDATION_ABUSE |
| I6 | Overlapping dates | 409 OVERLAP naming the conflicting request |
| I7 | Manager queue contains only direct reports' PENDING_MANAGER | exact set (priya's team absent) |
| I8 | Standard happy path: submit → manager approve | employee sees APPROVED + comment |
| I9 | Extended happy path: submit → manager approve → in HOD queue, not manager's → HOD approve | APPROVED; timeline has 3 entries |
| I10 | Reject with comment at HOD | REJECTED, comment visible to employee |
| I11 | Request-info loop; employee responds via multipart with a new document | returns to the asking stage; document attached |
| I12 | Two approvers decide the same request at once (two threads, separate DB connections) | one 200, one 409 STALE_VERSION; one decision row |
| I13 | Two overlapping submits by the same employee at once (two threads) | one 201, one 409 OVERLAP (employee row lock) |
| I14 | Pagination/filters on `/leaves/mine` and `/leaves/pending` | correct page/total/order |
| I15 | Audit row for every mutation above, same transaction; failure injected after the audit insert | rollback → no audit row, no change, stored blobs deleted |
| I16 | Malformed JSON, unknown fields, 70 KB JSON body | 422 / 413 friendly envelope, no Pydantic internals |
| I17 | Server error injected | 500 generic + requestId, no stack |
| I18 | `/api/healthz`, `/api/readyz` (DB up / DB down / migration head mismatch) | 200 / 503 SERVICE_UNAVAILABLE / 503 |
| I19 | `POST /leaves/preview` across chains | days/streak/isExtended/approvalChain correct; no rows written |
| I20 | Manager submits own leave | route HOD_ONLY, appears only in HOD queue |
| I21 | Password change: wrong current / weak / common / ok | 422 / 422 / 422 / 200 + other sessions revoked |
| I22 | Audit list filters + cursor pagination | correct |
| I23 | Demo account password change; demo user over the 20 MB quota | 403 FORBIDDEN; 413 QUOTA_EXCEEDED |

## 4. UI / UAT Script (manual, on the deployed link)
Run on production after release; record device/browser per run (§10.2).
1. Open the public URL on a phone → HTTPS padlock, login page, **demo banner** with accounts listed.
2. Login as **john** → Apply 1–3 Nov (3 days): no warning, submits, amber *Pending*.
3. Apply 10–14 Nov: orange *Extended* callout appears live; submit blocked until a document is attached; helper text explains why.
4. Attach an `.exe` renamed `.pdf` → rejected with a friendly message. Take a photo / choose a real PDF → submit succeeds.
5. On a **laptop**, login as **manager** → queue shows both; open the 5-day one → view document → **Approve with comment** → status for John becomes violet *Awaiting HOD*.
6. Manager queue no longer lists it. On a **tablet**, login as **hod** → queue lists it as "Step 2 of 2" → **Ask for info** → John (phone) sees sky *Info needed* banner → replies with a document → back to HOD queue → **Approve** → green *Approved*.
7. John's detail shows the full timeline. Manager rejects the 3-day one with comment → red *Rejected* + reason.
8. HOD opens **Audit log** → sees every step; filter by request id. Employee opening `/audit` gets a friendly 403 page.
9. Check 360 px phone (portrait + landscape) and tablet: bottom tab bar on phone, cards, no horizontal scroll. Toggle dark mode. Tab through the Apply form with keyboard only on desktop.
10. Airplane mode mid-submit on the phone → friendly offline message, input retained; reconnect → submit again → either created, or "You already submitted this (#id)".
11. (Free instance only) Leave the API idle ≥ 20 min, reload → "Waking up the server…" then normal login.

## 5. Security Tests (release gate — see SECURITY §16)
| # | Test | Expected |
|---|---|---|
| S1 | **IDOR matrix:** every `{id}`/`{docId}` endpoint × {owner, other employee, wrong manager (priya), right manager, HOD, anonymous} | only permitted cells succeed; others 404/401 |
| S2 | Default-deny: enumerate `app.routes`; each has a declared role dependency | test fails if undeclared |
| S3 | Tamper body: `status`, `days`, `isExtended`, `employeeId`, `role`, `streak` in payload | 422 (extra=forbid) + VALIDATION_ABUSE audit |
| S4 | Origin check: POST with `Origin: https://evil.example`; no Origin + `Sec-Fetch-Site: cross-site`; `text/plain` body; also on `/auth/login` | 403 / 403 / 415 / 403 |
| S5 | Session: cookie flags (HttpOnly, Secure in prod config, SameSite=Strict, Path=/, no Domain); new id on login; logout invalidates; idle/absolute expiry (fake clock); max 10 sessions | pass |
| S6 | Lockout & login limits: 5 bad passwords on a non-demo account → 429 RATE_LIMITED for 15 min, success resets; same on a demo account → not locked; > 20 attempts / 5 min from one IP → 429 | pass |
| S7 | SQLi payloads in every string field & query param (`' OR 1=1--`, `"; DROP`, `%_` in filters) | stored literally / rejected, no error leakage |
| S8 | XSS payloads in reason/comment/filename rendered by Detail and Audit pages (Vitest) | rendered as text; no element injected |
| S9 | Upload abuse: SVG, HTML, `.pdf` with exe bytes, DOCX with macro, zip-bomb DOCX, 4 files, 3 MB + 1 byte, `../../x` filename, null byte, double extension | 413/415 friendly error; storage keys only `docs/<uuid>` |
| S10 | Download headers: `attachment`, `nosniff`, `CSP: sandbox`, `no-store`; another user's doc id | as specified / 404 |
| S11 | Self-approval: manager approves own leave; employee calls the decision endpoint | blocked |
| S12 | Skip-HOD: extended + manager approve never reaches APPROVED | verified |
| S13 | Audit append-only: as the app DB user, `UPDATE`/`DELETE`/`TRUNCATE audit_log` → permission denied; as the test superuser → trigger raises | pass |
| S14 | API response headers (CSP, nosniff, XFO, Referrer-Policy, no `Server`) | present on success and error responses |
| S15 | Rate limits (slowapi) on mutating and upload routes | 429 envelope with `Retry-After` |
| S16 | Secrets: gitleaks (history); grep `frontend/dist` for `sb_`, `eyJ`, `service_role`, DSNs | none |
| S17 | Dependencies: pip-audit, `npm audit --audit-level=high` (optional bandit) | clean or accepted with expiry |
| S18 | CORS: requests with `Origin: https://evil.example` (simple + `OPTIONS` preflight) | no `Access-Control-Allow-*` headers ever |
| S19 | Open redirect: `/login?next=//evil.com`, `?next=https://evil.com` | lands on dashboard |
| S20 | Supabase exposure (once after setup, manual): call `/rest/v1/` with the project's anon key; fetch the bucket object via the public storage URL | no `leave` tables; object not readable |
| S21 | Body size: 70 KB JSON → 413; multipart over the cap → 413 | pass |
| S22 | Demo controls: `seed` refuses when `DEMO_MODE=false`; seed twice → no duplicates | pass |

## 6. Migrations & Database
| # | Test | Expected |
|---|---|---|
| MG1 | Empty DB: `alembic upgrade head` → `alembic check`; catalog query: RLS enabled on every `leave.*` table | succeeds; no drift between models and migrations; all true |
| MG2 | Single head (`alembic heads` = 1) | pass |
| MG3 | CHECK constraints (days formula, NEEDS_INFO ⇔ resume_status, extended ⇔ streak > 3) via raw SQL | rejected |

## 7. Storage
| # | Test | Expected |
|---|---|---|
| ST1 | `BlobStore` contract suite against the in-memory fake **and** MinIO | identical put/get/stream/delete behaviour |
| ST2 | Storage outage (MinIO stopped) during submit / download | 503 SERVICE_UNAVAILABLE; no DB rows left behind |

## 8. Deployment & Topology
| # | Test | Expected |
|---|---|---|
| DEP1 | Docker image: runs as UID 10001; `start.sh` migrates and seeds; a second start is a no-op; `readyz` 200 | pass |
| DEP2 | `docker compose up` from a clean clone → app on `http://localhost:5173` with seeded demo | works (README local steps verified) |
| DEP3 | Production settings guard: `APP_ENV=production` with `COOKIE_SECURE=false`, `sslmode=require`, http origin, missing `DEMO_PASSWORD` | refuses to boot with a clear message |
| DEP4 | Vercel: `/api/*` reaches the API; deep link `/requests/12` refresh serves the SPA; `/assets/*` immutable cache | pass |
| DEP5 | **Upload through the Vercel rewrite** (3 × 3 MB) — day-one check, then each release | succeeds, or limits lowered per ARCHITECTURE §12 |
| DEP6 | **Cold start** on a free instance: first request via Vercel after idle | UI shows wake notice; no error page (record the actual wait) |
| DEP7 | Cookie + Origin through the rewrite: login on iOS Safari and desktop Chrome; cookie host = app host; state-changing calls succeed | pass |

## 9. Post-Deploy Smoke Test (automated, production)
Runs in the `deploy` job after every deploy of `main`. Uses demo accounts and only read paths plus the
dry-run preview, so it creates no data. Requests send `Origin: <app URL>`.
| # | Check | Expected |
|---|---|---|
| SM1 | `GET /` over HTTPS | 200 with CSP, HSTS, XFO, nosniff headers |
| SM2 | `GET /api/readyz` | 200; `version` = deployed commit |
| SM3 | Login as john via the Vercel URL; `GET /auth/me` | 200; cookie HttpOnly, Secure, SameSite=Strict |
| SM4 | `POST /leaves/preview` for 4 days | `isExtended=true` |
| SM5 | `/api/docs`, `/api/openapi.json` | 404 |
| SM6 | Playwright smoke at 360 px and 1280 px (Chromium): login → dashboard renders → logout; no console errors or CSP violations | pass |

Failure → email alert; roll back to the previous deploy from the Render and Vercel dashboards.

## 10. Non-Functional (manual, modest)
### 10.1 Performance sanity
| # | Check | Target |
|---|---|---|
| P1 | Lighthouse mobile on the login page | LCP < 3 s, Accessibility ≥ 90 |
| P2 | Warm API, seeded data (+ ~1k extra requests from a seed flag): list/detail/queue timings in browser devtools | < 500 ms each; check `EXPLAIN` uses the indexes if not |

### 10.2 Cross-device matrix (real devices)
X1 iPhone Safari (full UAT §4) · X2 Android phone Chrome (full UAT) · X3 tablet, portrait + landscape
(UAT 5–9) · X4 laptop 1280–1440 px with Chrome, Edge, Firefox (full UAT). Per device: no horizontal
scroll, 44 px touch targets, native date and file/camera pickers, dark mode, cookie survives app switching.

### 10.3 Accessibility
axe in Vitest (FE8), Lighthouse (P1), a keyboard-only pass, one screen-reader pass (VoiceOver or NVDA),
200 % zoom reflow.

## 11. CI Mapping
| Job (ARCHITECTURE §9.5) | Suites |
|---|---|
| backend | U*, W*, unit §2.3, I*, S1–S7, S9–S15, S18, S19, S21, S22, MG*, ST*, S17 (pip-audit) |
| frontend | FE*, S8, lint/types, bundle grep (S16), S17 (npm audit) |
| security | S16 (gitleaks) |
| deploy (main → production) | SM1–SM6 |
| manual / one-off | UAT §4 on X1–X4, S20, DEP1–DEP7, P1–P2, §10.3 |

## 12. Entry / Exit Criteria
- **Entry:** CI green on `main`; migrations apply on an empty DB (MG1); walking skeleton reachable on the public URL; day-one checks (DEP5–DEP7) recorded.
- **Exit:** all unit/integration/security/migration/storage suites green; smoke §9 green; UAT §4 passes on X1–X4 against **production**; P1/P2 met; no open Sev-1/Sev-2; SECURITY §16 checklist ticked; README steps verified from a clean clone (DEP2) and by a reviewer on a phone using only the README.

## 13. Requirement Traceability
| Requirement (PRD) | Tests |
|---|---|
| Submit / view / status | I2, I14, FE2, UAT 2, 7 |
| Manager approve/reject/comment | I8, I10, W1, W6, UAT 5, 7 |
| View documents | I4, S10, UAT 5 |
| Attach documents (incl. phone camera) | I4, I11, FE2, S9, UAT 4, 6, X1–X2 |
| Ask for more info | W7, W8, I11, UAT 6 |
| >3 days → docs + Manager + HOD | U2–U4, U6–U8, I3, I4, I9, I19, W2–W5, W11, S12 |
| Manager's own leave → HOD | W16, I20 |
| Form validation | U10, U11, I3, I5, I6, I16, FE2, FE3 |
| No self-approval / hierarchy | W9, W10, I7, S1, S11 |
| Optimistic versioning / concurrency | W13, I12, I13, FE5 |
| Audit logs | I15, I22, S13, UAT 8 |
| Friendly errors | I3, I16, I17, FE3, FE9, UAT 4, 10, 11 |
| Colour coding / responsive / a11y | FE1, FE7, FE8, SM6, UAT 3, 5, 9, §10.2, §10.3 |
| Deployed public link (HTTPS, devices) | SM1–SM6, P1, X1–X4, DEP4–DEP7, UAT 1 |
| README (URL, creds, walkthrough, local dev) | DEP2, §12 exit criteria |
| Security NFR (internet-facing) | S1–S22, DEP3 |
| Demo environment controls | S6, S22, I23 |
