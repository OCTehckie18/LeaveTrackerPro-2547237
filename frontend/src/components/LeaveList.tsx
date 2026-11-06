import { Paperclip } from "lucide-react";
import { Link } from "react-router-dom";
import { formatRange, formatRangeShort, leaveTypeLabel, timeAgo } from "../lib/format";
import type { LeaveSummary } from "../lib/types";
import { Avatar, ExtendedTag, StatusBadge, TypeIcon, leaveKey } from "./ui";

function stepLabel(l: LeaveSummary): string | null {
  if (l.approverRoute !== "MANAGER_THEN_HOD") return null;
  if (l.status === "PENDING_MANAGER") return "Step 1 of 2";
  if (l.status === "PENDING_HOD") return "Step 2 of 2";
  return null;
}

/** One request as a GitHub-issues-style row: icon, bold title, lozenge, then a quiet meta line. */
export function LeaveRow({ l, showEmployee }: { l: LeaveSummary; showEmployee?: boolean }) {
  const step = stepLabel(l);
  return (
    <li className="group relative flex items-start gap-3 px-4 py-3 hover:bg-hover">
      <span className="mt-0.5">
        <TypeIcon type={l.leaveType} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Link
            to={`/requests/${l.id}`}
            className="font-semibold text-text after:absolute after:inset-0 hover:text-link hover:underline"
          >
            {formatRange(l.fromDate, l.toDate)}
          </Link>
          <StatusBadge status={l.status} />
          {l.isExtended && <ExtendedTag />}
        </div>
        <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted">
          <span className="font-medium">{leaveKey(l.id)}</span>
          <span aria-hidden="true">·</span>
          <span>
            {l.days} day{l.days === 1 ? "" : "s"} {leaveTypeLabel[l.leaveType].toLowerCase()}
          </span>
          <span aria-hidden="true">·</span>
          <span>
            {showEmployee ? `by ${l.employeeName}, ` : ""}updated {timeAgo(l.updatedAt)}
          </span>
          {step && (
            <>
              <span aria-hidden="true">·</span>
              <span className="font-medium text-hod-fg">{step}</span>
            </>
          )}
          {l.documentCount > 0 && (
            <>
              <span aria-hidden="true">·</span>
              <span className="inline-flex items-center gap-0.5">
                <Paperclip className="size-3" aria-hidden="true" />
                {l.documentCount}
              </span>
            </>
          )}
        </p>
      </div>
      {showEmployee && <Avatar name={l.employeeName} size="sm" />}
    </li>
  );
}

export function LeaveList({ items, showEmployee }: { items: LeaveSummary[]; showEmployee?: boolean }) {
  return (
    <ul className="divide-y divide-border">
      {items.map((l) => (
        <LeaveRow key={l.id} l={l} showEmployee={showEmployee} />
      ))}
    </ul>
  );
}

/** A Jira-board card. */
export function BoardCard({ l }: { l: LeaveSummary }) {
  return (
    <li>
      <Link
        to={`/requests/${l.id}`}
        className="block rounded-md border border-border bg-surface p-3 shadow-(--shadow-card) transition-shadow hover:bg-hover hover:shadow-(--shadow-pop)"
      >
        <p className="font-medium">{formatRangeShort(l.fromDate, l.toDate)}</p>
        <p className="mt-1 line-clamp-2 text-xs text-muted">{l.reason}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs text-muted">
          <TypeIcon type={l.leaveType} size="sm" />
          <span className="font-medium whitespace-nowrap">{leaveKey(l.id)}</span>
          {l.isExtended && <ExtendedTag />}
          <span className="ml-auto flex items-center gap-1.5">
            <span className="rounded-full bg-neutral-bg px-1.5 py-0.5 font-semibold text-neutral-fg">{l.days}d</span>
            <Avatar name={l.employeeName} size="xs" />
          </span>
        </div>
      </Link>
    </li>
  );
}
