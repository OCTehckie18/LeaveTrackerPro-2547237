import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  CalendarPlus,
  ClipboardCheck,
  History,
  LayoutDashboard,
  LogOut,
  ScrollText,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { ApiError, api } from "../lib/api";
import { MeProvider, useMe, useMeQuery } from "../lib/auth";
import { roleLabel } from "../lib/format";
import type { Role } from "../lib/types";
import { Avatar, ErrorBox, ListSkeleton } from "./ui";

interface NavItem {
  to: string;
  label: string;
  Icon: typeof LayoutDashboard;
  roles: Role[];
  badge?: "pending" | "info";
  section: "Workspace" | "Approvals" | "Administration";
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", Icon: LayoutDashboard, roles: ["EMPLOYEE", "MANAGER", "HOD"], section: "Workspace" },
  { to: "/apply", label: "Apply for leave", Icon: CalendarPlus, roles: ["EMPLOYEE", "MANAGER"], section: "Workspace" },
  { to: "/requests", label: "My requests", Icon: History, roles: ["EMPLOYEE", "MANAGER"], badge: "info", section: "Workspace" },
  { to: "/approvals", label: "Approval queue", Icon: ClipboardCheck, roles: ["MANAGER", "HOD"], badge: "pending", section: "Approvals" },
  { to: "/audit", label: "Audit log", Icon: ScrollText, roles: ["HOD"], section: "Administration" },
];

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2.5 font-semibold" aria-label="LeaveTrackerPro home">
      <span className="grid size-8 place-items-center rounded-md bg-linear-to-br from-[#1d7afc] to-[#5e4db2] text-white shadow-sm">
        <ShieldCheck className="size-[18px]" aria-hidden="true" />
      </span>
      {!compact && <span className="text-[15px] tracking-tight">LeaveTracker<span className="text-primary">Pro</span></span>}
    </Link>
  );
}

/** Gate for every signed-in page: loads the user, handles expiry and a sleeping server. */
export function RequireAuth() {
  const q = useMeQuery();
  const location = useLocation();
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!q.isPending) return;
    const t = setTimeout(() => setSlow(true), 3000);
    return () => clearTimeout(t);
  }, [q.isPending]);

  if (q.isPending)
    return (
      <div className="mx-auto max-w-3xl p-6">
        <p className="mb-4 text-center text-sm text-muted">
          {slow ? "Waking up the server (this can take up to a minute)…" : "Loading…"}
        </p>
        <ListSkeleton rows={4} />
      </div>
    );
  if (q.error instanceof ApiError && q.error.code === "UNAUTHENTICATED")
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (q.error || !q.data)
    return (
      <div className="mx-auto max-w-lg p-4">
        <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      </div>
    );

  return (
    <MeProvider value={q.data}>
      <Shell />
    </MeProvider>
  );
}

function UserMenu() {
  const me = useMe();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const location = useLocation();

  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const logout = useMutation({
    mutationFn: () => api.post("/auth/logout"),
    onSettled: () => {
      qc.clear();
      window.location.assign("/login");
    },
  });

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${me.user.name}`}
        className="grid size-9 place-items-center rounded-full ring-2 ring-transparent hover:ring-border"
      >
        <Avatar name={me.user.name} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-2 w-64 overflow-hidden rounded-md border border-border bg-surface shadow-(--shadow-pop)">
          <div className="flex items-center gap-3 border-b border-border p-3">
            <Avatar name={me.user.name} size="lg" />
            <div className="min-w-0">
              <p className="truncate font-semibold">{me.user.name}</p>
              <p className="truncate text-xs text-muted">{me.user.email}</p>
              <p className="mt-0.5 text-xs font-medium text-link">{roleLabel[me.user.role]}</p>
            </div>
          </div>
          <button
            type="button"
            role="menuitem"
            className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-sm hover:bg-hover md:min-h-9"
            onClick={() => logout.mutate()}
          >
            <LogOut className="size-4 text-muted" aria-hidden="true" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function Shell() {
  const me = useMe();
  const items = NAV.filter((n) => n.roles.includes(me.user.role));
  const sections = [...new Set(items.map((n) => n.section))];
  const canApply = me.user.role !== "HOD";
  const isApprover = me.user.role !== "EMPLOYEE";

  const count = (n: NavItem) =>
    n.badge === "pending" ? me.badges.pendingApprovals : n.badge === "info" ? me.badges.needsInfo : 0;
  const pill = (n: NavItem) =>
    count(n) > 0 ? (
      <span
        className={`ml-auto min-w-5 rounded-full px-1.5 text-center text-[11px] leading-5 font-bold ${
          n.badge === "pending" ? "bg-danger-fg text-surface" : "bg-info-fg text-surface"
        }`}
        aria-label={`${count(n)} need attention`}
      >
        {count(n)}
      </span>
    ) : null;

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[248px_1fr]">
      {/* Sidebar (desktop) */}
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-border bg-sunken md:flex">
        <div className="flex h-14 items-center px-4">
          <Logo />
        </div>
        <nav aria-label="Main" className="flex-1 space-y-5 overflow-y-auto px-3 py-2">
          {sections.map((s) => (
            <div key={s}>
              <p className="mb-1 px-2 text-[11px] font-bold tracking-wider text-muted uppercase">{s}</p>
              <ul className="space-y-0.5">
                {items
                  .filter((n) => n.section === s)
                  .map((n) => (
                    <li key={n.to}>
                      <NavLink
                        to={n.to}
                        end
                        className={({ isActive }) =>
                          `flex min-h-9 items-center gap-2.5 rounded-md px-2 text-sm font-medium ${
                            isActive ? "bg-selected text-link" : "text-text hover:bg-hover"
                          }`
                        }
                      >
                        <n.Icon className="size-4 shrink-0" aria-hidden="true" />
                        {n.label}
                        {pill(n)}
                      </NavLink>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </nav>
        {me.app.demoMode && (
          <div className="m-3 rounded-md border border-pending-fg/25 bg-pending-bg p-3 text-xs text-pending-fg">
            <p className="font-bold">Shared demo</p>
            <p className="mt-0.5">Please don't enter real personal or medical information. Data may be reset.</p>
          </div>
        )}
      </aside>

      <div className="flex min-w-0 flex-col">
        {/* Top bar */}
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-surface/90 px-4 backdrop-blur md:px-6">
          <div className="md:hidden">
            <Logo />
          </div>
          <div className="ml-auto flex items-center gap-2">
            {canApply && (
              <Link to="/apply" className="btn-primary">
                <CalendarPlus className="size-4" aria-hidden="true" />
                <span className="hidden sm:inline">Apply for leave</span>
                <span className="sm:hidden">Apply</span>
              </Link>
            )}
            <Link
              to={isApprover ? "/approvals" : "/requests"}
              className="relative grid size-9 place-items-center rounded-full text-muted hover:bg-hover"
              aria-label={`Notifications: ${me.badges.pendingApprovals + me.badges.needsInfo} need your attention`}
            >
              <Bell className="size-[18px]" aria-hidden="true" />
              {me.badges.pendingApprovals + me.badges.needsInfo > 0 && (
                <span className="absolute top-1 right-1 size-2.5 rounded-full bg-danger-fg ring-2 ring-surface" />
              )}
            </Link>
            <UserMenu />
          </div>
        </header>

        {me.app.demoMode && (
          <div className="border-b border-pending-fg/20 bg-pending-bg px-4 py-1.5 text-center text-xs text-pending-fg md:hidden">
            Shared demo: please don't enter real personal or medical information.
          </div>
        )}

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-6 pb-28 md:px-8 md:pb-12">
          <Outlet />
        </main>
      </div>

      {/* Bottom tabs (mobile) */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {items.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end
            className={({ isActive }) =>
              `relative flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium ${
                isActive ? "text-link" : "text-muted"
              }`
            }
          >
            <n.Icon className="size-5" aria-hidden="true" />
            <span>{n.label.replace("Apply for leave", "Apply").replace("Approval queue", "Approvals")}</span>
            {count(n) > 0 && (
              <span className="absolute top-1.5 left-1/2 ml-2 min-w-4 rounded-full bg-danger-fg px-1 text-center text-[10px] leading-4 font-bold text-surface">
                {count(n)}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

/** Role gate for pages only some roles may open. */
export function RequireRole({ roles }: { roles: Role[] }) {
  const me = useMe();
  if (!roles.includes(me.user.role))
    return (
      <div className="card mx-auto max-w-md p-8 text-center">
        <h1 className="text-lg font-semibold">You don't have access to this page</h1>
        <p className="mt-2 text-sm text-muted">It's meant for a different role.</p>
        <Link to="/" className="btn-primary mt-4">
          Go to dashboard
        </Link>
      </div>
    );
  return <Outlet />;
}
