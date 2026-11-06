import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarCheck, CalendarPlus, CircleHelp } from "lucide-react";
import { Link } from "react-router-dom";
import { BoardCard, LeaveRow } from "../components/LeaveList";
import { Avatar, EmptyState, ErrorBox, ListSkeleton, PageHeader, StatusBadge, leaveKey } from "../components/ui";
import { api } from "../lib/api";
import { useMe } from "../lib/auth";
import { daysBetween, formatDate, formatRange } from "../lib/format";
import type { LeaveSummary, Page, Status } from "../lib/types";

const COLUMNS: { status: Status; hint: string }[] = [
  { status: "PENDING_MANAGER", hint: "Waiting for your Manager" },
  { status: "PENDING_HOD", hint: "First approval done" },
  { status: "NEEDS_INFO", hint: "Your reply is needed" },
  { status: "APPROVED", hint: "Enjoy your time off" },
  { status: "REJECTED", hint: "See the reason inside" },
];

export default function Dashboard() {
  const me = useMe();
  const { user, badges } = me;
  const canApply = user.role !== "HOD";
  const first = user.name.split(" ")[0];

  const mine = useQuery({
    queryKey: ["mine", "dashboard"],
    queryFn: () => api.get<Page<LeaveSummary>>("/leaves/mine?size=50"),
    enabled: canApply,
  });
  const queue = useQuery({
    queryKey: ["pending", "dashboard"],
    queryFn: () => api.get<Page<LeaveSummary>>("/leaves/pending?size=5"),
    enabled: user.role !== "EMPLOYEE",
  });

  const items = mine.data?.items ?? [];
  const upcoming = items
    .filter((l) => l.status === "APPROVED" && l.toDate >= me.orgToday)
    .sort((a, b) => a.fromDate.localeCompare(b.fromDate))[0];
  const needsInfo = items.find((l) => l.status === "NEEDS_INFO");
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Workspace" }, { label: "Dashboard" }]}
        title={`${greeting}, ${first}`}
        subtitle={canApply ? "Your leave at a glance." : "Extended leave waits here for your final approval."}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        {needsInfo && (
          <Link
            to={`/requests/${needsInfo.id}`}
            className="flex items-center gap-3 rounded-md border border-info-fg/30 bg-info-bg p-4 text-info-fg lg:col-span-3"
          >
            <CircleHelp className="size-6 shrink-0" aria-hidden="true" />
            <span className="flex-1">
              <span className="block font-semibold">Your approver asked for more information</span>
              <span className="text-sm">Reply on {leaveKey(needsInfo.id)} to keep it moving.</span>
            </span>
            <ArrowRight className="size-5" aria-hidden="true" />
          </Link>
        )}

        {canApply && (
          <div className="card flex items-center gap-4 p-4">
            <span className="grid size-11 shrink-0 place-items-center rounded-md bg-success-bg text-success-fg">
              <CalendarCheck className="size-6" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-bold tracking-wide text-muted uppercase">Next time off</p>
              {mine.isPending ? (
                <p className="text-sm text-muted">Loading…</p>
              ) : upcoming ? (
                <>
                  <p className="truncate font-semibold">{formatRange(upcoming.fromDate, upcoming.toDate)}</p>
                  <p className="text-xs text-muted">
                    starts in {Math.max(0, daysBetween(me.orgToday, upcoming.fromDate) - 1)} days · {upcoming.days} days
                  </p>
                </>
              ) : (
                <p className="text-sm text-muted">Nothing booked yet</p>
              )}
            </div>
          </div>
        )}

        {user.role !== "EMPLOYEE" && (
          <div className={`card overflow-hidden ${canApply ? "lg:col-span-2" : "lg:col-span-3"}`}>
            <div className="flex items-center justify-between border-b border-border bg-sunken px-4 py-2.5">
              <h2 className="text-sm font-semibold">
                Needs your decision{" "}
                <span className="ml-1 rounded-full bg-danger-fg px-1.5 text-xs font-bold text-surface">{badges.pendingApprovals}</span>
              </h2>
              <Link to="/approvals" className="text-xs font-medium text-link hover:underline">
                Open queue →
              </Link>
            </div>
            {queue.isPending ? (
              <div className="p-4"><ListSkeleton rows={2} /></div>
            ) : queue.data && queue.data.items.length > 0 ? (
              <ul className="divide-y divide-border">
                {queue.data.items.map((l) => (
                  <LeaveRow key={l.id} l={l} showEmployee />
                ))}
              </ul>
            ) : (
              <p className="px-4 py-8 text-center text-sm text-muted">You're all caught up. Nothing is waiting for you.</p>
            )}
          </div>
        )}
      </div>

      {canApply && (
        <section className="mt-8" aria-labelledby="board-h">
          <div className="mb-3 flex items-center justify-between">
            <h2 id="board-h" className="text-base font-semibold">My leave board</h2>
            <Link to="/requests" className="text-xs font-medium text-link hover:underline">View all →</Link>
          </div>
          {mine.isPending && <ListSkeleton rows={3} />}
          {mine.error && <ErrorBox error={mine.error} onRetry={() => mine.refetch()} />}
          {mine.data &&
            (items.length === 0 ? (
              <EmptyState title="No leave requests yet" icon={<CalendarPlus className="size-7" />}>
                Apply for your first leave and track every approval step here.
                <div className="mt-4"><Link to="/apply" className="btn-primary">Apply for leave</Link></div>
              </EmptyState>
            ) : (
              <div className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-3 md:mx-0 md:px-0 lg:grid lg:grid-cols-5 lg:overflow-visible">
                {COLUMNS.map(({ status, hint }) => {
                  const col = items.filter((l) => l.status === status);
                  return (
                    <div key={status} className="w-64 shrink-0 snap-start rounded-md bg-sunken p-2 lg:w-auto">
                      <div className="mb-2 flex items-center justify-between px-1">
                        <StatusBadge status={status} />
                        <span className="text-xs font-semibold text-muted">{col.length}</span>
                      </div>
                      {col.length === 0 ? (
                        <p className="rounded-md border border-dashed border-border px-2 py-6 text-center text-xs text-muted">{hint}</p>
                      ) : (
                        <ul className="space-y-2">{col.map((l) => <BoardCard key={l.id} l={l} />)}</ul>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
        </section>
      )}

      {!canApply && (
        <div className="mt-6 flex items-center gap-3 rounded-md border border-border bg-sunken p-4 text-sm text-muted">
          <Avatar name={user.name} />
          <p>
            As Head of Department you give the final approval on extended leave and can review every action in the{" "}
            <Link to="/audit" className="font-medium text-link hover:underline">audit log</Link>. Last updated {formatDate(me.orgToday)}.
          </p>
        </div>
      )}
    </>
  );
}
