import type { LeaveType, Role, Route, Status } from "./types";

const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const dayFmt = new Intl.DateTimeFormat("en-GB", { weekday: "short" });
const dateTimeFmt = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** Parse a YYYY-MM-DD string as a LOCAL date (new Date("2026-11-01") would be UTC and can shift a day). */
export function parseDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export const formatDate = (iso: string) => dateFmt.format(parseDate(iso));
export const formatWeekday = (iso: string) => dayFmt.format(parseDate(iso));
export const formatDateTime = (iso: string) => dateTimeFmt.format(new Date(iso));

export function formatRange(from: string, to: string): string {
  return from === to ? formatDate(from) : `${formatDate(from)} → ${formatDate(to)}`;
}

const shortFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
/** "6 Dec → 10 Dec" (year only when it isn't the current year). */
export function formatRangeShort(from: string, to: string): string {
  const year = new Date().getFullYear();
  const f = parseDate(from), t = parseDate(to);
  const fmt = (d: Date) => (d.getFullYear() === year ? shortFmt.format(d) : formatDate(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`));
  return from === to ? fmt(f) : `${fmt(f)} → ${fmt(t)}`;
}

export function daysBetween(from: string, to: string): number {
  return Math.round((parseDate(to).getTime() - parseDate(from).getTime()) / 86_400_000) + 1;
}

export function formatBytes(n: number): string {
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function timeAgo(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export const leaveTypeLabel: Record<LeaveType, string> = {
  ANNUAL: "Annual",
  SICK: "Sick",
  CASUAL: "Casual",
  OTHER: "Other",
};

export const roleLabel: Record<Role, string> = {
  EMPLOYEE: "Employee",
  MANAGER: "Manager",
  HOD: "Head of Department",
};

export const routeSteps: Record<Route, string[]> = {
  MANAGER_ONLY: ["Manager"],
  MANAGER_THEN_HOD: ["Manager", "HOD"],
  HOD_ONLY: ["HOD"],
};

export const statusLabel: Record<Status, string> = {
  PENDING_MANAGER: "Pending",
  PENDING_HOD: "Awaiting HOD",
  NEEDS_INFO: "Info needed",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};
