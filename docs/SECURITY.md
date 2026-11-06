# LeaveTrackerPro — Security Design

Status: **Draft for review — rev 3 (simplified build, internet-facing)** · Date: 2026-11-06
Related: [PRD](PRD.md) · [ARCHITECTURE](ARCHITECTURE.md) · [DESIGN](DESIGN.md) · [TEST_PLAN](TEST_PLAN.md)
Baseline: OWASP Top 10 (2021) and OWASP API Security Top 10 (2023). Test IDs refer to [TEST_PLAN](TEST_PLAN.md).

## 1. Threat Model
### 1.1 Assets, threats and primary mitigations
| Asset | Main threats | Mitigation (section) |
|---|---|---|
| Credentials / sessions | brute force, credential stuffing, fixation, XSS theft, CSRF | argon2id, per-IP limit + account lockout, HttpOnly SameSite=Strict cookie, Origin check, strict CSP (§2–4, §8) |
| Leave records & reasons (may be medical) | IDOR, privilege escalation, SQLi, leakage in logs/errors | object checks in SQL, 404 for not-yours, bound parameters, redacted logs (§5, §6, §12) |
| Uploaded documents | malicious files, unauthorised download, stored XSS via SVG/HTML | allow-list + magic bytes + DOCX checks, private bucket, attachment download (§7) |
| Approval integrity | self-approval, skipping HOD, races, forged `employeeName` | pure state machine, server-derived fields, row locks + version (§5, §6, §10) |
| Audit log | tampering, deletion, repudiation | append-only: no UPDATE/DELETE privilege + blocking triggers (§11) |
| Infrastructure secrets (DSN, S3 keys, deploy hook) | leakage via repo, bundle, logs, CI | platform secret stores, gitleaks, bundle grep (§14) |
| Public demo availability | bots, DoS, free-tier exhaustion, storage abuse | rate limits, body/file limits, quota, platform DDoS protection (§8, §15) |

Other threats: **SSRF** — no feature fetches user-supplied URLs; **CORS** — disabled (§8.5);
**clickjacking** — `frame-ancestors 'none'` + `X-Frame-Options: DENY`; **open redirect** — `next` limited to
relative paths (§8.8); **dependency CVEs** — pip-audit, npm audit, Dependabot (§14).

Trust boundary: everything from the browser is untrusted — role, user id, employee name, status, `days`,
`isExtended`, `streak` are **never read from the request**; they are derived server-side.

### 1.2 Attack surface
| Surface | Controls |
|---|---|
| `https://<app>.vercel.app/*` static SPA | CDN, strict headers (§8.2), no secrets in bundle |
| `https://<app>.vercel.app/api/*` (rewritten to Render) | session auth, Origin check, rate limits, validation, authz |
| `https://<svc>.onrender.com` (public origin URL) | same controls; the cookie is never sent there; client-IP caveat (§8.4) |
| Supabase Postgres pooler | strong password, TLS `verify-full`, RLS on all tables (§9) |
| Supabase Data API / Storage HTTP API | `leave` schema not exposed, RLS with no policies, private bucket, anon key unused (§9) |
| GitHub repo & Actions | gitleaks, repository secrets, Dependabot (§14) |

## 2. Authentication
**Decision:** backend-owned authentication with server-side sessions (ARCHITECTURE ADR-2).
- **Hashing:** argon2id via **argon2-cffi** `PasswordHasher` (library defaults; `check_needs_rehash` on
  login upgrades old hashes).
- **Password policy:** 12–128 characters, no composition rules, no forced rotation; rejected if it
  contains the email local part or is in a bundled common/breached-password list (top 100k).
- **Login throttling:** per IP 20 attempts / 5 min (slowapi, §8.7); per account, 5 consecutive failures →
  `locked_until = now() + 15 min` (counter in `users.failed_logins`, reset on success, `LOGIN_LOCKOUT`
  audit). **Demo accounts are exempt from lockout** so strangers can't lock shared accounts; the per-IP
  limit still applies. Errors are generic ("Email or password is incorrect", 401) or 429 `RATE_LIMITED`
  with `Retry-After`; unknown emails are checked against a dummy hash so timing reveals nothing.
- **Lifecycle:** **self-signup disabled** (no registration endpoint). Users come from
  `python -m app.cli create-user` (random initial password shown once); `app.cli reset-password` for
  forgotten passwords; deactivation deletes all sessions.
- **Password change** (`POST /auth/password`): needs the current password; deletes other sessions; new
  session id; audit `PASSWORD_CHANGED`; forbidden for demo accounts.
- **MFA:** documented extension (TOTP); not in v1 because demo accounts are shared by design.

## 3. Session Management
- Token `secrets.token_urlsafe(32)`; **only its SHA-256 is stored**, so a DB leak doesn't hand out sessions.
- Cookie `lt_session=<token>; Path=/; Secure; HttpOnly; SameSite=Strict`, **no `Domain`** (host-only).
  Because the browser talks to the Vercel host, the cookie belongs to the app host only. `Secure` is off
  only in local http dev. `*.vercel.app` is on the Public Suffix List, so sibling apps can't touch it.
- Idle timeout 30 min, absolute 8 h; new token on login (anti-fixation); logout deletes the row; password
  change/deactivation deletes all sessions; max 10 sessions per user (oldest removed).
- Role and manager are read from the DB on every request → changes apply immediately.
- `Cache-Control: no-store` on all `/api` responses.

## 4. CSRF & Origin Verification
1. `SameSite=Strict` cookie — cross-site requests don't carry the session.
2. **Origin check** on every non-GET/HEAD request, login included: `Origin` must exactly match
   `ALLOWED_ORIGINS`; if absent, `Sec-Fetch-Site` must be `same-origin`; otherwise 403 `FORBIDDEN` +
   `ORIGIN_REJECTED` audit.
3. Mutating routes accept only `application/json` or `multipart/form-data` (415 otherwise).

*Why no separate anti-CSRF token:* on a same-origin app with a Strict, host-only cookie and a strict
Origin check, a token adds code without closing a remaining gap. Add one if the app ever goes cross-site.

## 5. Authorisation (the most important section)
Policy lives in `domain/policy.py` and is enforced in the **service layer + SQL predicates**, never only in
the UI. The API is the only path to the data (§9).

| Rule | Enforcement |
|---|---|
| Employee sees only own requests | `WHERE employee_id = :session_user` |
| Manager sees/decides only direct reports' requests at stage MANAGER | join on `users.manager_id = :me` in the query |
| HOD decides only stage HOD for their department | join through manager → HOD (`approver_route` aware) |
| No self-approval | `actor_id != request.employee_id` in `transition()`; manager's own leave routes to HOD |
| Cannot skip the HOD step | extended + MANAGER APPROVE → `PENDING_HOD` only; no endpoint sets status directly |
| Documents only for owner + current/previous approvers | same predicate as request detail, not URL secrecy |
| Not yours → **404**, not 403 | stops enumeration of sequential ids |
| Audit log | HOD read-only; no write API |

Every route declares its role via `Depends(require_role(...))`; a test fails on any route without one (S2).

## 6. Input Validation & Injection
- **Pydantic v2** models with `extra="forbid"`, whitespace stripping, strict types (no `"1"`→1); dates
  **only** as `YYYY-MM-DD` (rejects `2026-02-30`, `2026/11/01`, unix timestamps); enums as `Literal`;
  length limits via `Field`. The multipart `data` part is parsed with the same model.
- Server-derived fields (`status`, `days`, `isExtended`, `employeeId`, `role`) are absent from request
  models → 422 + `VALIDATION_ABUSE` audit (S3).
- **SQL:** SQLAlchemy with bound parameters only (ruff `S608`); sort/filter columns from allow-lists;
  `LIKE` filters escape `%`/`_`.
- Reason/comment: trimmed, length-bounded, control chars (except `\n`) rejected. React escapes output.
- **SSRF:** no endpoint takes a URL; the only outbound call is the S3 client to the configured endpoint.

## 7. File Upload & Storage Security
**Decision:** files arrive with the leave (or reply) in one multipart request; downloads are **streamed
through the API** (ARCHITECTURE ADR-4). The browser never sees storage credentials or URLs.
1. **Limits:** PDF, PNG, JPEG, DOCX only; ≤ 3 files per request; ≤ 3 MB each (reading stops at limit + 1
   byte → 413); demo quota 20 MB per user.
2. **Magic bytes** (`%PDF-`, PNG signature, JPEG `FF D8 FF`, ZIP `PK\x03\x04`) decide the type; the
   client's `Content-Type`/extension is ignored. DOCX must contain `[Content_Types].xml` +
   `word/document.xml`, no `vbaProject.bin`, ≤ 200 entries and ≤ 50 MB uncompressed (zip-bomb guard).
3. **Storage:** private bucket `leave-documents`, accessed only server-side via the S3 API with keys in
   Render secrets. Object key `docs/<uuid4>` — never user-derived. Original filename is sanitised display
   metadata only (basename, no control chars/`..`/separators, ≤ 120 chars).
4. **Download:** authorised; `Content-Type` from the DB; `Content-Disposition: attachment` (inline only for
   PDF/PNG/JPEG on request); `X-Content-Type-Options: nosniff`; `Content-Security-Policy: sandbox;
   default-src 'none'`; `Cache-Control: private, no-store`; audit `DOC_DOWNLOADED`.
5. **Integrity:** SHA-256 recorded; blobs from a failed transaction are deleted. Malware scanning is an
   extension (§17).

## 8. Transport, Headers, CORS, Limits
### 8.1 TLS & HSTS
TLS on every hop: browser ↔ Vercel, Vercel ↔ Render (HTTPS origin), API ↔ Postgres (`sslmode=verify-full`
with the Supabase CA), API ↔ Storage. HTTP redirects to HTTPS. `Strict-Transport-Security:
max-age=63072000; includeSubDomains` in `vercel.json`; preload only with an owned custom domain.

### 8.2 Headers at the host (`vercel.json`)
```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self';
  img-src 'self' blob: data:; font-src 'self'; connect-src 'self'; object-src 'none';
  base-uri 'none'; form-action 'self'; frame-ancestors 'none'
Strict-Transport-Security: max-age=63072000; includeSubDomains
X-Content-Type-Options: nosniff · X-Frame-Options: DENY · Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cache-Control: no-cache (index.html) / public, max-age=31536000, immutable (/assets/*)
```
Vite emits external hashed JS/CSS and theme bootstrap is the external `/theme-init.js`, so `script-src
'self'` needs no nonces. Photo capture uses the OS file picker, which `camera=()` doesn't block.

### 8.3 Headers at the API (every response, including errors)
`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` (downloads: `sandbox` variant),
`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`,
`X-Request-ID`; no `Server` header.

### 8.4 Client IP
The slowapi key function reads `X-Forwarded-For`, skips the `TRUSTED_PROXY_HOPS` right-most entries
(measured on day one) and uses the next one. **Known limitation:** the Render origin URL is public, so a
direct caller can forge `X-Forwarded-For` and dodge per-IP limits; account lockout and validation still
apply. Restricting the origin to Vercel traffic is future work.

### 8.5 CORS
**Disabled:** the API sends no `Access-Control-Allow-*` headers. `ALLOWED_ORIGINS` is used only by the
Origin check, exact-match, no wildcards.

### 8.6 Request limits
Body-size middleware (64 KB JSON; multipart ≤ `MAX_UPLOAD_FILES × MAX_UPLOAD_MB` + 64 KB, checked on
`Content-Length` and while reading); DB `statement_timeout` 5 s; bounded pool; list `size` ≤ 50;
`python-multipart` kept current (past DoS CVEs); Vercel platform DDoS mitigation.

### 8.7 Rate limiting (slowapi, in-memory)
One instance, one worker → exact counters. **Honest limits:** counters reset on restart/redeploy and would
be wrong with more instances or workers; the scale path is slowapi's Redis storage (e.g. Upstash).
Exceeded limits return 429 `RATE_LIMITED` with `Retry-After`.

| Bucket (per client IP) | Limit |
|---|---|
| `POST /auth/login` | 20 / 5 min |
| `POST /leaves`, `POST /leaves/{id}/respond` (carry files) | 20 / hour |
| other mutating routes | 60 / min |
| all API routes (default) | 300 / 5 min |

### 8.8 Navigation safety
`/login?next=` accepts only `^/(?!/)[A-Za-z0-9/_-]*$` (relative; `//evil` and absolute URLs rejected).

## 9. Database Security (Supabase / PostgreSQL)
- **One DB user** for the API (ARCHITECTURE §4.1) via the session pooler with TLS `verify-full`; password
  only in a Render secret; DSN never logged.
- **RLS enabled on every table in `leave`, no policies.** The API's owner connection bypasses RLS (the API
  is the only data path and enforces §5); `anon`/`authenticated` via the Data API get nothing. Plus `REVOKE
  ALL ON SCHEMA leave FROM anon, authenticated, public`; `leave` not exposed (MG1, S20).
- **Never expose the `service_role`/secret key to the browser** — the app doesn't use it at all (no
  Supabase client SDK). Neither the anon key nor any Supabase URL is in the SPA bundle.
- **Storage:** private bucket; S3 keys bypass Storage policies, so treat them like a root storage
  credential.
- Supabase dashboard members use MFA. Future: separate least-privilege runtime role, request-scoped RLS
  policies, network restrictions.

## 10. Concurrency & Integrity
- **Decisions:** `FOR UPDATE` on the request row + optimistic `version` → no double approval or lost update (I12).
- **Overlap/streak:** `FOR UPDATE` on the employee's `users` row serialises that employee's submits, so
  checks see committed neighbours (I13). Relies on all writes using the service; a DB exclusion constraint
  is future hardening.
- `CHECK` constraints mirror invariants: date order, `days` formula, status enum, NEEDS_INFO ⇔
  `resume_status`, `is_extended ⇔ streak > 3` (MG3).

## 11. Audit Logging
Events: LOGIN_SUCCESS/FAILURE/LOCKOUT, LOGOUT, PASSWORD_CHANGED, LEAVE_SUBMITTED, DOC_UPLOADED/DOWNLOADED,
APPROVED (stage), REJECTED, INFO_REQUESTED, INFO_RESPONDED, CANCELLED, AUTHZ_DENIED, VALIDATION_ABUSE,
ORIGIN_REJECTED, AUDIT_VIEWED. Each row: UTC time, actor, role, action, entity, before→after status,
request id, IP. No reason/comment text.
- Written in the **same transaction** as the business change (I15).
- **Append-only:** the app user has `INSERT`/`SELECT` only; `BEFORE UPDATE OR DELETE` and `BEFORE TRUNCATE`
  triggers raise (S13).
- Honest scope: this stops the app (and bugs or injection through it) from changing history. A DB owner
  could disable the trigger; tamper-*evidence* is the hash-chain stretch goal (ARCHITECTURE §11).

## 12. Error Handling & Disclosure
Generic 500 with request id; stack traces only in logs; FastAPI default handlers overridden (no Pydantic
internals or input echo); identical response for unknown vs wrong credentials; 404 for unauthorised
objects; API docs off in production; logs never contain passwords, cookies, reasons, comments or files.

## 13. Privacy
Data minimisation (no DOB/address/phone). Reasons and documents never in logs, URLs or analytics.
Supabase encrypts Postgres and Storage at rest. Region `ap-southeast-1` (confirm against policy). Real
deployment retention (configurable): records 7 years, documents purged N days after the final decision.
Demo: no real personal data (banner).

## 14. Secrets, Supply Chain & CI
- **Secrets** only in platform stores: Render (`DATABASE_URL`, S3 keys, `DEMO_PASSWORD`) and GitHub Actions
  (`RENDER_DEPLOY_HOOK_URL`). Vercel holds only non-secret `VITE_*` values. `.env` git-ignored.
- **CI:** gitleaks + GitHub push protection; grep of `frontend/dist` for key patterns (S16); pip-audit and
  `npm audit --audit-level=high` (S17); ruff (incl. `S` rules), mypy, ESLint (`jsx-a11y`, no
  `dangerouslySetInnerHTML`); optional bandit; Dependabot weekly; `permissions: contents: read`; fork PRs
  get no secrets.
- **Container:** multi-stage slim image, non-root UID 10001.

## 15. Demo Environment (published credentials)
| Risk | Mitigation |
|---|---|
| Anyone can log in as any role | dedicated Supabase project/bucket; no real data; no admin features |
| Real PII entered by visitors | banner "Don't enter real personal or medical information"; manual reset possible |
| Account takeover / lockout griefing | demo accounts can't change password, are exempt from lockout (per-IP limits still apply); max 10 sessions |
| Storage abuse | 20 MB per-user quota, upload rate limit, allow-list, attachment-only downloads, participants-only access |
| Bots / free-tier exhaustion | rate limits, `robots.txt` Disallow, uptime alerts |
| Credential reuse | demo password used nowhere else; rotate via `DEMO_PASSWORD`/`VITE_DEMO_PASSWORD` + redeploy |
| Demo seeding a real deployment | `DEMO_MODE` defaults to false; `seed` refuses otherwise (S22) |

## 16. Release Checklist (gate)
- [ ] Default-deny routes (S2) · [ ] IDOR matrix (S1) · [ ] Self-approval / skip-HOD (S11, S12)
- [ ] Origin check (S4) · [ ] Cookie flags (S5, SM3) · [ ] Cookie + Origin through the rewrite (DEP7)
- [ ] No CORS headers (S18) · [ ] Lockout & rate limits (S6, S15)
- [ ] Upload abuse (S9) · [ ] Download headers (S10) · [ ] Bucket private + Data API not exposed (S20)
- [ ] Audit append-only (S13) · [ ] RLS enabled on all tables (MG1) · [ ] Headers on host + API (S14, SM1)
- [ ] gitleaks + bundle grep (S16) · [ ] pip-audit / npm audit (S17)
- [ ] Production guard: docs off, `COOKIE_SECURE=true`, `sslmode=verify-full`, `DEMO_MODE` intentional (DEP3, SM5)
- [ ] Development secrets rotated; Supabase dashboard MFA on

## 17. Residual Risks / Accepted
- **Single API instance, in-memory limiter:** counters reset on restart; scaling needs a shared store (§8.7).
- **Public Render origin:** direct callers can forge `X-Forwarded-For` to dodge per-IP limits (§8.4).
- **Free tiers:** Render cold starts, no SLA, Supabase Free pauses when idle (uptime monitor helps), no
  managed backups, no stable egress IPs.
- **Shared demo credentials** (§15) — accepted for assessment only.
- **No malware scanning**; **no MFA/SSO** in v1.
- **Audit is append-only, not tamper-evident** against a DB owner.
- **One DB user** for migrations and runtime; RLS doesn't catch an API query bug (authz lives in the API).
- S3 keys are bucket-wide: compromise of the API host exposes all documents.
- **Unverified until day one** (ARCHITECTURE §12): Vercel rewrite body limit and timeout, cookie and
  `Origin` through the rewrite, `X-Forwarded-For` hops, Render free-tier sleep/wake behaviour.
