import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ClipboardCheck, ScrollText, Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { LeaveList } from "../components/LeaveList";
import { Avatar, EmptyState, ErrorBox, ListSkeleton, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { formatDateTime, statusLabel, timeAgo } from "../lib/format";
import type { AuditPage, LeaveSummary, Page, Status } from "../lib/types";

function Pager({ page, size, total, onPage }: { page: number; size: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (pages <= 1) return null;
  return (
    <nav className="flex items-center justify-between border-t border-border bg-sunken px-4 py-2.5" aria-label="Pagination">
      <button type="button" className="btn-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
      <span className="text-xs text-muted">Page {page} of {pages} · {total} total</span>
      <button type="button" className="btn-secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
    </nav>
  );
}

const FILTERS: (Status | "ALL")[] = ["ALL", "PENDING_MANAGER", "PENDING_HOD", "NEEDS_INFO", "APPROVED", "REJECTED", "CANCELLED"];

/** The signed-in person's own requests, newest first. */
export function History() {
  const [status, setStatus] = useState<Status | "ALL">("ALL");
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ["mine", status, page],
    queryFn: () =>
      api.get<Page<LeaveSummary>>(`/leaves/mine?page=${page}&size=10${status === "ALL" ? "" : `&status=${status}`}`),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Workspace" }, { label: "My requests" }]}
        title="My requests"
        subtitle="Everything you've submitted, newest first."
      />
      <div className="card overflow-hidden">
        <div className="flex gap-1 overflow-x-auto border-b border-border bg-sunken p-2" role="group" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={status === f}
              onClick={() => { setStatus(f); setPage(1); }}
              className={`min-h-9 shrink-0 rounded-md px-3 text-sm font-medium whitespace-nowrap ${
                status === f ? "bg-surface text-text shadow-(--shadow-card)" : "text-muted hover:bg-hover hover:text-text"
              }`}
            >
              {f === "ALL" ? "All" : statusLabel[f]}
            </button>
          ))}
        </div>
        {q.isPending && <div className="p-4"><ListSkeleton rows={4} /></div>}
        {q.error && <div className="p-4"><ErrorBox error={q.error} onRetry={() => q.refetch()} /></div>}
        {q.data &&
          (q.data.items.length === 0 ? (
            <div className="px-6 py-14 text-center">
              <p className="font-semibold">Nothing here yet</p>
              <p className="mt-1 text-sm text-muted">
                {status === "ALL" ? "Apply for leave to see it listed here." : "No requests with this status."}
              </p>
            </div>
          ) : (
            <>
              <LeaveList items={q.data.items} />
              <Pager page={page} size={q.data.size} total={q.data.total} onPage={setPage} />
            </>
          ))}
      </div>
    </>
  );
}

/** Requests waiting for the signed-in approver, oldest first. */
export function Approvals() {
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ["pending", page],
    queryFn: () => api.get<Page<LeaveSummary>>(`/leaves/pending?page=${page}&size=10`),
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <PageHeader
        crumbs={[{ label: "Approvals" }, { label: "Queue" }]}
        title="Approval queue"
        subtitle="Requests waiting for your decision, oldest first."
      />
      <div className="card overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border bg-sunken px-4 py-2.5 text-sm font-semibold">
          <ClipboardCheck className="size-4 text-muted" aria-hidden="true" />
          {q.data ? `${q.data.total} waiting` : "Loading…"}
        </div>
        {q.isPending && <div className="p-4"><ListSkeleton rows={3} /></div>}
        {q.error && <div className="p-4"><ErrorBox error={q.error} onRetry={() => q.refetch()} /></div>}
        {q.data &&
          (q.data.items.length === 0 ? (
            <div className="px-6 py-14 text-center">
              <p className="font-semibold">You're all caught up</p>
              <p className="mt-1 text-sm text-muted">Nothing is waiting for your decision.</p>
            </div>
          ) : (
            <>
              <LeaveList items={q.data.items} showEmployee />
              <Pager page={page} size={q.data.size} total={q.data.total} onPage={setPage} />
            </>
          ))}
      </div>
    </>
  );
}

function dotClass(action: string): string {
  if (/APPROVED|SUCCESS|SUBMITTED|PASSWORD/.test(action)) return "bg-success-fg";
  if (/REJECTED|FAILURE|LOCKOUT|DENIED|ABUSE/.test(action)) return "bg-danger-fg";
  if (/INFO/.test(action)) return "bg-info-fg";
  return "bg-neutral-fg";
}

/** HOD only: the append-only audit trail. */
export function Audit() {
  const [entityId, setEntityId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [scope, setScope] = useState<"leave_request" | "user" | "">("leave_request");
  const params = new URLSearchParams();
  if (scope) params.set("entity", scope);
  if (entityId.trim()) params.set("entityId", entityId.trim());
  if (from) params.set("from", from);
  if (to) params.set("to", to);

  const q = useInfiniteQuery({
    queryKey: ["audit", scope, entityId, from, to],
    queryFn: ({ pageParam }) => {
      const p = new URLSearchParams(params);
      if (pageParam) p.set("cursor", String(pageParam));
      return api.get<AuditPage>(`/audit?${p}`);
    },
    initialPageParam: 0,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
  const rows = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Administration" }, { label: "Audit log" }]}
        title="Audit log"
        subtitle="Every important action, newest first. Read-only: nobody can edit or delete these records."
      />
      <div className="card overflow-hidden">
        <div className="flex gap-1 border-b border-border bg-sunken p-2" role="group" aria-label="Event type">
          {([["leave_request", "Leave requests"], ["user", "Sign-ins"], ["", "Everything"]] as const).map(([v, label]) => (
            <button
              key={label}
              type="button"
              aria-pressed={scope === v}
              onClick={() => setScope(v)}
              className={`min-h-9 rounded-md px-3 text-sm font-medium whitespace-nowrap ${
                scope === v ? "bg-surface text-text shadow-(--shadow-card)" : "text-muted hover:bg-hover hover:text-text"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="grid gap-3 border-b border-border bg-sunken p-3 pt-1 sm:grid-cols-[1.4fr_1fr_1fr]">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted" aria-hidden="true" />
            <label htmlFor="a-id" className="sr-only">Request number</label>
            <input id="a-id" inputMode="numeric" className="input pl-8" value={entityId} onChange={(e) => setEntityId(e.target.value)} placeholder="Filter by request number, e.g. 12" />
          </div>
          <div>
            <label htmlFor="a-from" className="sr-only">From date</label>
            <input id="a-from" type="date" className="input" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div>
            <label htmlFor="a-to" className="sr-only">To date</label>
            <input id="a-to" type="date" className="input" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </div>

        {q.isPending && <div className="p-4"><ListSkeleton rows={4} /></div>}
        {q.error && <div className="p-4"><ErrorBox error={q.error} onRetry={() => q.refetch()} /></div>}
        {q.data && rows.length === 0 && (
          <div className="px-6 py-14 text-center">
            <ScrollText className="mx-auto mb-2 size-8 text-muted" aria-hidden="true" />
            <p className="font-semibold">No matching events</p>
          </div>
        )}
        {rows.length > 0 && (
          <ul className="divide-y divide-border">
            {rows.map((r) => (
              <li key={r.id} className="flex gap-3 px-4 py-3 text-sm">
                <Avatar name={r.actorName ?? "System"} size="sm" />
                <div className="min-w-0 flex-1">
                  <p>
                    <span className="font-semibold">{r.actorName ?? "Anonymous"}</span>{" "}
                    <span className="text-muted">{r.action.replaceAll("_", " ").toLowerCase()}</span>
                    {r.entityType === "leave_request" && r.entityId && (
                      <> on <Link className="font-medium text-link hover:underline" to={`/requests/${r.entityId}`}>LT-{r.entityId}</Link></>
                    )}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
                    <span aria-hidden="true" className={`inline-block size-2 rounded-full ${dotClass(r.action)}`} />
                    <time dateTime={r.ts} title={formatDateTime(r.ts)}>{timeAgo(r.ts)}</time>
                    {r.actorRole && <span>{r.actorRole.toLowerCase()}</span>}
                  </p>
                  {Object.keys(r.details).filter((k) => k !== "seed").length > 0 && (
                    <p className="mt-1.5 flex flex-wrap gap-1.5">
                      {Object.entries(r.details)
                        .filter(([k]) => k !== "seed")
                        .map(([k, v]) => (
                          <span key={k} className="rounded-[3px] bg-sunken px-1.5 py-0.5 font-mono text-[11px] text-muted">
                            {k}={String(v)}
                          </span>
                        ))}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        {q.hasNextPage && (
          <div className="border-t border-border bg-sunken p-3">
            <button type="button" className="btn-secondary w-full" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage}>
              {q.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          </div>
        )}
      </div>
    </>
  );
}

export function NotFound() {
  return (
    <div className="mx-auto max-w-md">
      <EmptyState title="We couldn't find that page">
        It may have moved, or the link is incorrect.
        <div className="mt-4"><Link to="/" className="btn-primary">Go to dashboard</Link></div>
      </EmptyState>
    </div>
  );
}
