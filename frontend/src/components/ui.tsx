import {
  Ban,
  CalendarDays,
  CircleCheck,
  CircleHelp,
  CircleX,
  Clock,
  HeartPulse,
  Coffee,
  Sun,
  TriangleAlert,
  UserCheck,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../lib/api";
import { statusLabel } from "../lib/format";
import type { LeaveType, Status } from "../lib/types";

// Static class strings so Tailwind can see them. Colour + icon + text: never colour alone.
const STATUS_STYLE: Record<Status, { cls: string; Icon: typeof Clock }> = {
  PENDING_MANAGER: { cls: "bg-pending-bg text-pending-fg", Icon: Clock },
  PENDING_HOD: { cls: "bg-hod-bg text-hod-fg", Icon: UserCheck },
  NEEDS_INFO: { cls: "bg-info-bg text-info-fg", Icon: CircleHelp },
  APPROVED: { cls: "bg-success-bg text-success-fg", Icon: CircleCheck },
  REJECTED: { cls: "bg-danger-bg text-danger-fg", Icon: CircleX },
  CANCELLED: { cls: "bg-neutral-bg text-neutral-fg", Icon: Ban },
};

/** Jira-style status lozenge: small, square-cornered, uppercase. */
export function StatusBadge({ status }: { status: Status }) {
  const { cls, Icon } = STATUS_STYLE[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-[3px] px-1.5 py-0.5 text-[11px] font-bold tracking-wide whitespace-nowrap uppercase ${cls}`}
    >
      <Icon className="size-3" aria-hidden="true" />
      {statusLabel[status]}
    </span>
  );
}

export function ExtendedTag() {
  return (
    <span className="inline-flex items-center gap-1 rounded-[3px] border border-ext/40 bg-ext-bg px-1.5 py-0.5 text-[11px] font-bold tracking-wide whitespace-nowrap text-ext uppercase">
      <TriangleAlert className="size-3" aria-hidden="true" />
      Extended
    </span>
  );
}

const TYPE_STYLE: Record<LeaveType, { cls: string; Icon: typeof Sun; label: string }> = {
  ANNUAL: { cls: "bg-success-fg", Icon: Sun, label: "Annual" },
  SICK: { cls: "bg-danger-fg", Icon: HeartPulse, label: "Sick" },
  CASUAL: { cls: "bg-primary", Icon: Coffee, label: "Casual" },
  OTHER: { cls: "bg-neutral-fg", Icon: CalendarDays, label: "Other" },
};

/** Like Jira's issue-type icon: a small coloured square. */
export function TypeIcon({ type, size = "md" }: { type: LeaveType; size?: "sm" | "md" | "lg" }) {
  const { cls, Icon, label } = TYPE_STYLE[type];
  const box = size === "lg" ? "size-8" : size === "sm" ? "size-4" : "size-5";
  const ico = size === "lg" ? "size-[18px]" : size === "sm" ? "size-2.5" : "size-3";
  return (
    <span
      title={`${label} leave`}
      className={`grid shrink-0 place-items-center rounded-[4px] text-surface ${box} ${cls}`}
    >
      <Icon className={ico} aria-hidden="true" />
      <span className="sr-only">{label} leave</span>
    </span>
  );
}

const AVATAR_COLORS = [
  "bg-[#0c66e4] text-white",
  "bg-[#6e5dc6] text-white",
  "bg-[#1f845a] text-white",
  "bg-[#c25100] text-white",
  "bg-[#ae2e24] text-white",
  "bg-[#0b7c8c] text-white",
  "bg-[#a6288f] text-white",
];

export function Avatar({ name, size = "md" }: { name: string; size?: "xs" | "sm" | "md" | "lg" }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  const dim =
    size === "xs" ? "size-5 text-[9px]" : size === "sm" ? "size-6 text-[10px]" : size === "lg" ? "size-10 text-sm" : "size-8 text-xs";
  return (
    <span
      aria-hidden="true"
      title={name}
      className={`grid shrink-0 place-items-center rounded-full font-semibold ${dim} ${AVATAR_COLORS[hash % AVATAR_COLORS.length]}`}
    >
      {initials}
    </span>
  );
}

/** Issue-key style reference, e.g. LT-12. */
export const leaveKey = (id: number) => `LT-${id}`;

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="card divide-y divide-border">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 p-4">
          <Skeleton className="size-5" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="h-5 w-20" />
        </div>
      ))}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="space-y-3 py-6">
      <p className="text-center text-sm text-muted">{label}…</p>
      <ListSkeleton rows={3} />
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
  const ref = error instanceof ApiError && error.requestId && error.status >= 500 ? ` (reference: ${error.requestId})` : "";
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-danger-fg/30 bg-danger-bg p-4 text-danger-fg">
      <TriangleAlert className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <div className="flex-1">
        <p className="font-medium">
          {msg}
          {ref}
        </p>
        {onRetry && (
          <button type="button" className="btn-secondary mt-3 text-text" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, icon, children }: { title: string; icon?: ReactNode; children?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-14 text-center">
      <div className="mb-2 grid size-14 place-items-center rounded-full bg-sunken text-muted">
        {icon ?? <CalendarDays className="size-7" aria-hidden="true" />}
      </div>
      <p className="text-base font-semibold">{title}</p>
      {children && <div className="max-w-sm text-sm text-muted">{children}</div>}
    </div>
  );
}

export interface Crumb {
  label: string;
  to?: string;
}

export function PageHeader({
  title,
  subtitle,
  action,
  crumbs,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  crumbs?: Crumb[];
}) {
  return (
    <div className="mb-5">
      {crumbs && (
        <nav aria-label="Breadcrumb" className="mb-2 flex flex-wrap items-center gap-1 text-xs text-muted">
          {crumbs.map((c, i) => (
            <span key={c.label} className="flex items-center gap-1">
              {i > 0 && <span aria-hidden="true">/</span>}
              {c.to ? (
                <Link to={c.to} className="hover:text-link hover:underline">
                  {c.label}
                </Link>
              ) : (
                <span aria-current="page">{c.label}</span>
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight md:text-2xl">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        </div>
        {action}
      </div>
    </div>
  );
}

export function FieldError({ message }: { message?: string }) {
  return message ? (
    <p className="field-error" role="alert">
      {message}
    </p>
  ) : null;
}
