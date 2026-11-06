# LeaveTrackerPro — UI/UX Design

Status: **Draft for review — rev 3 (React + Vite + Tailwind v4, no component framework)** · Date: 2026-11-06
Related: [PRD](PRD.md) · [ARCHITECTURE](ARCHITECTURE.md) · [SECURITY](SECURITY.md) · [TEST_PLAN](TEST_PLAN.md)

## 1. Principles
1. **Clarity first:** the status of a request is understood in one glance (colour + icon + text).
2. **Guide, don't scold:** validation is inline, specific and helpful; the extended-leave rule is explained *before* the user hits an error.
3. **Mobile-first, any device:** designed at 360 px, scaled to tablet and laptop; touch targets ≥ 44 px; works with touch, mouse, keyboard and screen readers.
4. **Accessible:** WCAG 2.1 AA; colour is never the only indicator.
5. **Fast on mobile networks:** static, code-split SPA from a CDN; skeletons instead of spinners; the server is the source of truth.
6. **Secure by construction:** React escaping only (no `dangerouslySetInnerHTML`), no tokens in JS storage, CSP-compatible build (no inline scripts/styles in `index.html`).

## 2. Colour System (Tailwind v4 `@theme` tokens)
Semantic tokens are CSS variables switched by theme; Tailwind utilities are generated from them with
`@theme inline`, so `bg-pending-bg text-pending-fg` etc. follow light/dark automatically.

| Token (utility suffix) | Light fg / bg | Dark fg / bg | Use |
|---|---|---|---|
| `primary` | #2563EB / — | #60A5FA / — | Actions, links, focus ring |
| `pending` | #B45309 (amber) / #FEF3C7 | #FCD34D / #451A03 | PENDING_MANAGER ("Pending") |
| `pending-hod` | #6D28D9 (violet) / #EDE9FE | #C4B5FD / #2E1065 | PENDING_HOD ("Awaiting HOD") |
| `info` | #0369A1 (sky) / #E0F2FE | #7DD3FC / #082F49 | NEEDS_INFO ("Info needed") |
| `success` | #15803D (green) / #DCFCE7 | #86EFAC / #052E16 | APPROVED |
| `danger` | #B91C1C (red) / #FEE2E2 | #FCA5A5 / #450A0A | REJECTED, errors |
| `muted` | #475569 (slate) / #F1F5F9 | #CBD5E1 / #1E293B | CANCELLED |
| `extended` | #C2410C (orange) outline | #FDBA74 outline | "Extended leave" tag |
| `surface` / `ink` | #FFFFFF / #0F172A | #0F172A / #E2E8F0 | page / text |

Every fg/bg pair ≥ 4.5:1 (checked by a small contrast unit test over the token values, TEST_PLAN FE7).

```css
/* src/styles/app.css — Tailwind v4, CSS-first; no tailwind.config.js */
@import "tailwindcss";

/* class-based dark mode, defaulting to the OS preference (set by /theme-init.js) */
@custom-variant dark (&:where(.dark, .dark *));

:root {                       /* light values from the table; same names for every token */
  --c-primary: #2563eb;
  --c-pending-fg: #b45309;  --c-pending-bg: #fef3c7;
  /* … pending-hod, info, success, danger, muted, extended, surface, ink … */
}
.dark {
  --c-primary: #60a5fa;
  --c-pending-fg: #fcd34d;  --c-pending-bg: #451a03;
  /* … dark values per table … */
}
@theme inline {               /* generates bg-pending-bg, text-pending-fg, … */
  --color-primary: var(--c-primary);
  --color-pending-fg: var(--c-pending-fg);  --color-pending-bg: var(--c-pending-bg);
  /* … one line per token … */
}
@theme { --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif; }  /* self-hosted woff2 */
```
Vite: `plugins: [react(), tailwindcss()]` with `import tailwindcss from "@tailwindcss/vite"`.
Theme switching: `public/theme-init.js` (external, tiny) adds `.dark` to `<html>` from a saved preference
(`localStorage.theme`, UI preference only) or `prefers-color-scheme`. It is an external file rather than an
inline snippet, so the CSP needs no `'unsafe-inline'`. A header toggle offers Light / Dark / System.

**Status badge** = `[icon] Label` using lucide-react icons (`aria-hidden`, text always present):
`Clock` Pending · `UserCheck` Awaiting HOD · `MessageCircleQuestion` Info needed · `CircleCheck` Approved ·
`CircleX` Rejected · `Ban` Cancelled · `CalendarRange` Extended. One `<StatusBadge status>` component maps
status → token + icon + label (exhaustive `switch` on the API's status union).
Stepper for extended leave: `Submitted → Manager → HOD → Done` with completed steps green, current step in
its status colour, future steps grey; `aria-current="step"` on the active step.

## 3. Information Architecture
```
/login
/                 → redirect by role (employee → /employee, manager/HOD → /approvals)
/employee         Dashboard (summary chips + latest) · /apply · /requests (history) · /requests/:id
/approvals        Manager & HOD: queue · /approvals/:id (decision screen)
/audit            HOD only
/settings         Change password (hidden for demo accounts), theme
*                 Friendly 404
```
React Router with **history** URLs (deep links work across devices); Vercel serves `index.html` for
unknown paths (ARCHITECTURE §9.2). A route guard checks the role from `/auth/me` and redirects to `/login`
with `?next=` restricted to same-origin relative paths (no open redirect).
Navigation is role-aware: top bar (≥ 1024 px), compact top bar on tablet, **bottom tab bar** on phones
(< 640 px) with safe-area padding.

## 4. Screens
### 4.0 App shell & demo banner
Header: app name, role pill, theme toggle, user menu (settings, logout). When `VITE_DEMO_MODE=true`, the
login page shows an amber banner: "Demo environment — shared accounts below. Don't enter real personal or
medical information. Data may be reset." with a table of the demo accounts (email, role, team) and the
published demo password (PRD §8). A smaller version of the banner stays in the app shell.
"Waking up the server…" inline notice appears if `/api/healthz` takes > 3 s (cold start, ARCHITECTURE §9.6).

### 4.1 Login
Centered card, email + password (`autocomplete="username"` / `"current-password"`), show/hide password,
friendly errors ("Email or password is incorrect" — never revealing which; lockout shows "Too many
attempts. Try again in 15 minutes."). Password managers work (real `<form>`, proper names).

### 4.2 Employee Dashboard
Chips: *Pending n · Awaiting HOD n · Info needed n · Approved n*. Highlighted callout if any request is
NEEDS_INFO: "Your manager asked for more information → Respond". Recent 5 requests. Floating "Apply"
button on phones.

### 4.3 Apply for Leave
```
┌ Apply for leave ───────────────────────────┐
│ Name         John (read-only, from login)   │
│ Leave type   [Annual ▾]                     │
│ From [2026-11-01]   To [2026-11-05]         │
│ ┌ ⚠ Extended leave · 5 days ──────────────┐ │   ← appears live (via /leaves/preview) when streak > 3
│ │ Needs supporting documents and approval │ │
│ │ from your Manager and your HOD.         │ │
│ └─────────────────────────────────────────┘ │
│ Reason  [textarea]            0/500         │
│ Documents  [Take photo / Choose file]  (required)│
│   medical.pdf  1.2 MB  ✕   (max 3 files, 3 MB each)│
│ [Cancel]                    [Submit request]│
└─────────────────────────────────────────────┘
```
- Form: react-hook-form + zod mirroring PRD §5.2 ("today" = `orgToday` from `/auth/me`). The server
  re-validates; its field errors are mapped back onto the same inputs (`setError`).
- Native `<input type="date">` (best mobile pickers), `min=today`; "To" min = From.
- Live day counter "5 days (Sat–Wed)" and chain note "This joins your approved leave on 31 Oct → 6 days
  in a row", from a debounced (300 ms) `/leaves/preview` query.
- File picker: `<input type="file" accept="application/pdf,image/png,image/jpeg,.docx" multiple>` (phones
  offer camera/photos). Files are listed with size and a remove button and **sent with the form** as one
  multipart request. Instant client checks ("medical.jpg is 4.1 MB — the limit is 3 MB. Try a smaller
  photo or a PDF."); the server re-checks by content.
- Submit is disabled-with-reason: helper text says what's missing (`aria-describedby`); "Submitting…"
  while in flight.
- Network failure keeps fields and files; "Try again" resubmits. If the first attempt had succeeded, the
  `OVERLAP` answer shows as "You already submitted this (#id) — view it". Text fields are also kept as a
  `sessionStorage` draft across session expiry.

### 4.4 My Requests (history)
Desktop/tablet landscape: table (ID, Dates, Days, Type, Status badge, Updated). Phone/tablet portrait:
stacked cards with the badge top-right. Filter chips by status, pagination, empty state ("No leave requests
yet — Apply for leave"). Data via `useQuery(['leaves','mine',filters])`, `placeholderData` keeps the
previous page while loading.

### 4.5 Request Detail (employee)
Header with badge + stepper; details; documents list; **Timeline** (vertical): who, what, when, comment
bubble (manager comments in blue, rejection reason in a red callout). If NEEDS_INFO: reply box + file
picker (same limits), sent as one request. Cancel button opens a confirm `<ConfirmDialog>`.

### 4.6 Approvals Queue (Manager/HOD)
Cards/table sorted oldest first: employee, dates, days, `Extended` tag, "Step 1 of 2" / "Step 2 of 2",
docs count (`Paperclip`), waiting-since. Overdue (> 3 days waiting) gets amber "Waiting 4 days" text.
Nav badge shows queue count (polled every 60 s + on window focus).

### 4.7 Decision Screen
Left: request facts, reason, employee's recent leave (last 5), documents (PNG/JPEG preview as `<img>` from
the authorised download URL; PDF opens in a new tab via `?disposition=inline`, served with `CSP: sandbox`;
DOCX download only), earlier comments.
Right (sticky bottom panel on mobile): comment box + three buttons: **Approve** (green), **Ask for info**
(sky), **Reject** (red). Comment-required hint appears on Reject/Ask. A confirm dialog summarises the
consequence: "Approving will send this to the HOD for final approval."
If extended and no docs: Approve is disabled with an explanation.
Stale-version conflict (409 `STALE_VERSION`) → non-destructive banner "Updated by someone else — refresh"
keeping the typed comment.

### 4.8 Audit Log (HOD)
Filterable table: time, actor, role, action, entity, details (expandable, shown as text), request id.
Colour dot per action category. Cursor pagination ("Load more"). Export CSV (stretch).

### 4.9 Settings
Change password (current + new + confirm, strength hint, common-password message from the server). Hidden
for demo accounts with an explanation. Theme selector.

## 5. Feedback & Friendly Errors
- Toasts: a small `<Toaster>` component rendering into an `aria-live="polite"` region, for success
  messages; inline field errors with `aria-describedby`; a top error summary on submit failure focusing the
  first invalid field.
- Central `apiFetch` maps the error envelope (ARCHITECTURE §6) → UI: `fields` → form errors; `message` →
  toast/banner; `requestId` shown as "Reference: …" for 500/503.
- Network down / timeout → "We couldn't reach the server. Your input is kept — try again."
- Cold start (slow first response) → "Waking up the server… this can take up to a minute the first time."
- 401 → redirect to `/login?next=…` with "Your session expired. Please sign in again."
- 403/404 → friendly pages with a "Go to dashboard" action. 413 → "Files are too large (max 3 files, 3 MB
  each)." 429 → "Too many attempts — try again in {Retry-After}." 500 → "Something went wrong on our
  side. Reference: {requestId}".
- Copy tone: plain, specific, actionable; no codes shown to users except the reference id.

## 6. Responsive Behaviour
| Breakpoint (Tailwind) | Devices | Layout |
|---|---|---|
| base < 640 (`sm`) | phones 360–430 px | single column, bottom tab bar, cards instead of tables, sticky action bar |
| `sm`–`lg` 640–1024 | tablets, small laptops | two-column forms, compact table, side-by-side detail on landscape |
| ≥ `lg` 1024 | laptops/desktops | max-width 1100 px container, side-by-side detail/decision |

CSS grid/flex, no horizontal scroll, `env(safe-area-inset-*)` for notched phones, `100dvh` for full-height
panels (iOS toolbar), respects `prefers-reduced-motion`, inputs ≥ 16 px font to avoid iOS zoom-on-focus,
hover-only affordances always have a tap equivalent.

## 7. Accessibility Checklist
Semantic landmarks · labels on every control · visible focus ring (`focus-visible:ring-primary`) · dialogs
use native `<dialog>` with `showModal()` (built-in focus handling and Esc; focus returned to the trigger
on close) · badges include text · tables have `scope` headers and become labelled cards on mobile · errors
announced via `aria-live="polite"` · route changes move focus to the page `<h1>` and update
`document.title` · keyboard-only pass and one screen-reader pass (VoiceOver or NVDA) before release · axe
checks in Vitest.

## 8. Front-end Code Structure (`frontend/`)
```
index.html                 shell; only external <script type="module"> and /theme-init.js (CSP-safe)
public/                    theme-init.js · favicon · robots.txt (Disallow: /)
vite.config.ts             react(), tailwindcss(); dev server.proxy /api → API
vercel.json                /api rewrite, SPA fallback, security headers
src/
  main.tsx                 QueryClientProvider, RouterProvider, Toaster
  app/router.tsx           routes, role guard, error boundaries
  app/layout/              AppShell, TopNav, BottomTabBar, DemoBanner, WakeNotice
  api/client.ts            apiFetch: credentials 'same-origin', JSON or FormData bodies,
                           error envelope → ApiError, 401 handling
  api/schema.d.ts          generated from OpenAPI (openapi-typescript) — do not edit
  api/queries.ts           TanStack Query hooks (useMyLeaves, usePending, useLeave, …)
  features/auth/           LoginPage, useSession, ChangePasswordPage
  features/leaves/         ApplyPage, HistoryPage, DetailPage, RespondForm, schemas.ts (zod)
  features/approvals/      QueuePage, DecisionPage, DecisionPanel
  features/audit/          AuditPage
  components/ui/           StatusBadge, Stepper, Timeline, FilePicker, DataTable/CardList,
                           ConfirmDialog (<dialog>), Toaster, FieldError, EmptyState
  lib/                     dates (org-TZ helpers), format, constants (limits mirrored from PRD §5.2)
  styles/app.css           Tailwind import + tokens (§2)
  test/                    setup.ts (Testing Library, jest-dom, vitest-axe), msw handlers
e2e/smoke.spec.ts          Playwright smoke (TEST_PLAN §9)
```
- **Server state** only in TanStack Query (no global store); mutations invalidate `['leaves']`/`['pending']`;
  `retry` only for GETs; `refetchOnWindowFocus` keeps multi-device views fresh.
- **XSS:** text rendered through JSX only; ESLint bans `dangerouslySetInnerHTML`; URLs built only from API
  ids (`encodeURIComponent`).
- **No secrets:** CI greps `dist/` for `sb_`, `eyJ`, `service_role`, DSNs. The demo password is public by
  design and labelled as such.
