import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, FileImage, FileText, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Dialog } from "../components/Dialog";
import { FileDrop } from "../components/FileDrop";
import { Stepper } from "../components/Stepper";
import { Timeline } from "../components/Timeline";
import { useToast } from "../components/Toast";
import {
  Avatar,
  ErrorBox,
  ExtendedTag,
  FieldError,
  ListSkeleton,
  StatusBadge,
  TypeIcon,
  leaveKey,
} from "../components/ui";
import { ApiError, api, documentUrl } from "../lib/api";
import { useMe } from "../lib/auth";
import {
  formatBytes,
  formatDate,
  formatDateTime,
  formatWeekday,
  leaveTypeLabel,
  statusLabel,
  timeAgo,
} from "../lib/format";
import type { DecisionAction, LeaveDetail as Leave } from "../lib/types";

const ACTION_TEXT: Record<DecisionAction, { title: string; button: string; cls: string; needsComment: boolean }> = {
  APPROVE: { title: "Approve this request?", button: "Approve", cls: "btn-success", needsComment: false },
  REQUEST_INFO: { title: "Ask for more information?", button: "Ask for info", cls: "btn-info", needsComment: true },
  REJECT: { title: "Reject this request?", button: "Reject", cls: "btn-danger", needsComment: true },
};

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_1fr] items-center gap-2 py-2 text-sm">
      <dt className="text-xs font-semibold text-muted">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-2">
      <h2 id={id} className="text-sm font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export default function LeaveDetail() {
  const { id } = useParams();
  const me = useMe();
  const q = useQuery({
    queryKey: ["leave", id],
    queryFn: () => api.get<Leave>(`/leaves/${id}`),
    retry: (n, e) => !(e instanceof ApiError && e.status < 500 && e.status !== 0) && n < 2,
  });

  if (q.isPending) return <ListSkeleton rows={4} />;
  if (q.error instanceof ApiError && q.error.status === 404)
    return (
      <div className="card mx-auto max-w-md p-8 text-center">
        <h1 className="text-lg font-semibold">We couldn't find that request</h1>
        <p className="mt-2 text-sm text-muted">It doesn't exist, or it isn't one you can see.</p>
        <Link to="/" className="btn-primary mt-4">Go to dashboard</Link>
      </div>
    );
  if (q.error) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;

  const leave = q.data;
  const isOwner = leave.employeeId === me.user.id;
  const question = [...leave.decisions].reverse().find((d) => d.action === "REQUEST_INFO");
  const waiting =
    leave.permissions.waitingFor === "MANAGER" ? "Manager" : leave.permissions.waitingFor === "HOD" ? "Head of Department" : null;

  return (
    <div>
      <nav aria-label="Breadcrumb" className="mb-3 flex flex-wrap items-center gap-1 text-xs text-muted">
        <Link to="/" className="hover:text-link hover:underline">Workspace</Link>
        <span aria-hidden="true">/</span>
        <Link to={isOwner ? "/requests" : "/approvals"} className="hover:text-link hover:underline">
          {isOwner ? "My requests" : "Approval queue"}
        </Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page" className="font-medium text-text">{leaveKey(leave.id)}</span>
      </nav>

      <div className="mb-6 flex items-start gap-3">
        <TypeIcon type={leave.leaveType} size="lg" />
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold tracking-tight md:text-2xl">
            {formatDate(leave.fromDate)}
            {leave.fromDate !== leave.toDate && <> – {formatDate(leave.toDate)}</>}
          </h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-muted">
            <span className="font-medium">{leaveKey(leave.id)}</span>
            <StatusBadge status={leave.status} />
            {leave.isExtended && <ExtendedTag />}
            <span>
              {leave.days} day{leave.days === 1 ? "" : "s"} of {leaveTypeLabel[leave.leaveType].toLowerCase()} leave
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        {/* ---- main column ---- */}
        <div className="min-w-0 space-y-6">
          {leave.status === "NEEDS_INFO" && isOwner && question && (
            <div role="status" className="flex gap-3 rounded-md border border-info-fg/30 bg-info-bg p-4 text-info-fg">
              <Avatar name={question.actorName} />
              <div>
                <p className="font-semibold">{question.actorName} asked for more information</p>
                <p className="mt-1 text-sm whitespace-pre-wrap">{question.comment}</p>
              </div>
            </div>
          )}

          <div className="card p-4 md:p-5">
            <Stepper leave={leave} />
            {waiting && (
              <p className="mt-3 text-center text-xs text-muted">
                Waiting for the {waiting}
                {leave.approverRoute === "MANAGER_THEN_HOD" && ` · step ${leave.permissions.waitingFor === "MANAGER" ? 1 : 2} of 2`}
              </p>
            )}
          </div>

          <Section id="reason-h" title="Reason">
            <div className="card px-4 py-3 text-sm whitespace-pre-wrap">{leave.reason}</div>
          </Section>

          <Section id="docs-h" title={`Attachments${leave.documents.length ? ` (${leave.documents.length})` : ""}`}>
            {leave.documents.length === 0 ? (
              <p className="rounded-md border border-dashed border-border px-4 py-5 text-center text-sm text-muted">
                {leave.isExtended ? "No documents attached yet." : "No documents attached."}
              </p>
            ) : (
              <ul className="grid gap-3 sm:grid-cols-2">
                {leave.documents.map((d) => {
                  const Icon = d.mime.startsWith("image/") ? FileImage : FileText;
                  const previewable = d.mime !== "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
                  return (
                    <li key={d.id} className="card flex items-center gap-3 p-3">
                      <span className="grid size-10 shrink-0 place-items-center rounded-md bg-info-bg text-info-fg">
                        <Icon className="size-5" aria-hidden="true" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{d.name}</p>
                        <p className="text-xs text-muted">{formatBytes(d.sizeBytes)} · {timeAgo(d.createdAt)}</p>
                      </div>
                      {previewable && (
                        <a className="btn-subtle px-2" href={documentUrl(leave.id, d.id, true)} target="_blank" rel="noopener noreferrer" aria-label={`View ${d.name}`}>
                          <Eye className="size-4" aria-hidden="true" />
                        </a>
                      )}
                      <a className="btn-subtle px-2" href={documentUrl(leave.id, d.id)} aria-label={`Download ${d.name}`}>
                        <Download className="size-4" aria-hidden="true" />
                      </a>
                    </li>
                  );
                })}
              </ul>
            )}
          </Section>

          {leave.permissions.canDecide && <DecisionPanel leave={leave} />}
          {leave.permissions.canRespond && <RespondPanel leave={leave} />}

          <Section id="tl-h" title="Activity">
            <Timeline decisions={leave.decisions} />
          </Section>
        </div>

        {/* ---- details panel ---- */}
        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start" aria-label="Details">
          <div className="card">
            <h2 className="border-b border-border px-4 py-2.5 text-sm font-semibold">Details</h2>
            <dl className="divide-y divide-border px-4">
              <DetailRow label="Status"><StatusBadge status={leave.status} /></DetailRow>
              {waiting && <DetailRow label="Waiting on">{waiting}</DetailRow>}
              <DetailRow label="Requested by">
                <span className="flex items-center gap-2"><Avatar name={leave.employeeName} size="sm" />{leave.employeeName}</span>
              </DetailRow>
              <DetailRow label="Leave type">
                <span className="flex items-center gap-2"><TypeIcon type={leave.leaveType} size="sm" />{leaveTypeLabel[leave.leaveType]}</span>
              </DetailRow>
              <DetailRow label="From">{formatWeekday(leave.fromDate)}, {formatDate(leave.fromDate)}</DetailRow>
              <DetailRow label="To">{formatWeekday(leave.toDate)}, {formatDate(leave.toDate)}</DetailRow>
              <DetailRow label="Duration">
                {leave.days} day{leave.days === 1 ? "" : "s"}
                {leave.streak > leave.days && <span className="block text-xs text-ext">{leave.streak} days in a row with neighbouring leave</span>}
              </DetailRow>
              <DetailRow label="Approval path">
                {leave.approverRoute === "MANAGER_THEN_HOD" ? "Manager, then HOD" : leave.approverRoute === "HOD_ONLY" ? "HOD" : "Manager"}
              </DetailRow>
              <DetailRow label="Created"><span title={formatDateTime(leave.createdAt)}>{timeAgo(leave.createdAt)}</span></DetailRow>
              <DetailRow label="Updated"><span title={formatDateTime(leave.updatedAt)}>{timeAgo(leave.updatedAt)}</span></DetailRow>
            </dl>
          </div>

          {!isOwner && leave.recentLeave.length > 0 && (
            <div className="card">
              <h2 className="border-b border-border px-4 py-2.5 text-sm font-semibold">{leave.employeeName.split(" ")[0]}'s other leave</h2>
              <ul className="divide-y divide-border">
                {leave.recentLeave.map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-2 px-4 py-2 text-xs">
                    <span>
                      <span className="font-semibold">{leaveKey(r.id)}</span> · {formatDate(r.fromDate)} ({r.days}d)
                    </span>
                    <span className="text-muted">{statusLabel[r.status]}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {leave.permissions.canCancel && <CancelPanel leave={leave} />}
        </aside>
      </div>
    </div>
  );
}

/** After any change: store the fresh request and refresh lists/badges. */
function useAfterChange(leave: Leave) {
  const qc = useQueryClient();
  return (fresh: Leave) => {
    qc.setQueryData(["leave", String(leave.id)], fresh);
    qc.invalidateQueries({ queryKey: ["mine"] });
    qc.invalidateQueries({ queryKey: ["pending"] });
    qc.invalidateQueries({ queryKey: ["me"] });
  };
}

/** A Jira-style comment box: avatar + one bordered surface with the actions underneath. */
function CommentBox({ title, tone, children }: { title: string; tone: "primary" | "info"; children: React.ReactNode }) {
  const me = useMe();
  return (
    <section aria-label={title} className="flex gap-3">
      <Avatar name={me.user.name} />
      <div
        className={`min-w-0 flex-1 overflow-hidden rounded-md border bg-surface shadow-(--shadow-card) ${
          tone === "info" ? "border-info-fg/40" : "border-primary/50"
        }`}
      >
        <div className={`border-b px-3 py-2 text-sm font-semibold ${tone === "info" ? "border-info-fg/20 bg-info-bg text-info-fg" : "border-border bg-selected text-link"}`}>
          {title}
        </div>
        <div className="space-y-3 p-3">{children}</div>
      </div>
    </section>
  );
}

function DecisionPanel({ leave }: { leave: Leave }) {
  const toast = useToast();
  const qc = useQueryClient();
  const after = useAfterChange(leave);
  const [comment, setComment] = useState("");
  const [action, setAction] = useState<DecisionAction | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const noDocs = leave.isExtended && leave.documentCount === 0;
  const firstOfTwo = leave.status === "PENDING_MANAGER" && leave.approverRoute === "MANAGER_THEN_HOD";

  const decide = useMutation({
    mutationFn: (a: DecisionAction) =>
      api.post<Leave>(`/leaves/${leave.id}/decision`, { action: a, comment: comment.trim() || null, version: leave.version }),
    onSuccess: (fresh, a) => {
      after(fresh);
      setAction(null);
      setComment("");
      toast(
        a === "APPROVE"
          ? fresh.status === "PENDING_HOD" ? "Approved. Sent to the HOD for final approval." : "Request approved."
          : a === "REJECT" ? "Request rejected." : "Question sent to the employee.",
      );
    },
    onError: (e) => {
      setAction(null);
      if (e instanceof ApiError) {
        toast(e.fields.comment ?? e.message, "error");
        if (e.code === "STALE_VERSION" || e.code === "INVALID_TRANSITION") qc.invalidateQueries({ queryKey: ["leave", String(leave.id)] });
      }
    },
  });

  function open(a: DecisionAction) {
    if (ACTION_TEXT[a].needsComment && comment.trim().length < 5) {
      setProblem(a === "REJECT" ? "Please tell the employee why you're rejecting this." : "Please write the question for the employee.");
      return;
    }
    setProblem(null);
    setAction(a);
  }

  return (
    <CommentBox title={`Your decision${leave.approverRoute === "MANAGER_THEN_HOD" ? ` · step ${firstOfTwo ? 1 : 2} of 2` : ""}`} tone="primary">
      {noDocs && (
        <p className="flex gap-2 rounded-md bg-ext-bg p-3 text-sm text-ext">
          <TriangleAlert className="size-5 shrink-0" aria-hidden="true" />
          This extended request has no documents, so it can't be approved. Ask the employee to add one.
        </p>
      )}
      <div>
        <label htmlFor="comment" className="sr-only">Comment</label>
        <textarea
          id="comment"
          rows={3}
          maxLength={1000}
          className="input"
          placeholder="Add a comment (required to reject or ask for information)…"
          value={comment}
          onChange={(e) => { setComment(e.target.value); setProblem(null); }}
        />
        <FieldError message={problem ?? undefined} />
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-success" disabled={noDocs || decide.isPending} onClick={() => open("APPROVE")}>Approve</button>
        <button type="button" className="btn-info" disabled={decide.isPending} onClick={() => open("REQUEST_INFO")}>Ask for info</button>
        <button type="button" className="btn-danger" disabled={decide.isPending} onClick={() => open("REJECT")}>Reject</button>
      </div>

      <Dialog open={action !== null} title={action ? ACTION_TEXT[action].title : ""} onClose={() => setAction(null)}>
        <p className="text-sm text-muted">
          {action === "APPROVE" && (firstOfTwo ? "Approving will send this to the HOD for final approval." : "The employee will see this as approved.")}
          {action === "REJECT" && "This is final. The employee will see your comment."}
          {action === "REQUEST_INFO" && "The request pauses until the employee replies."}
        </p>
        {comment.trim() && <p className="mt-3 rounded-md bg-sunken p-3 text-sm whitespace-pre-wrap">{comment.trim()}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn-subtle" onClick={() => setAction(null)}>Go back</button>
          {action && (
            <button type="button" className={ACTION_TEXT[action].cls} disabled={decide.isPending} onClick={() => decide.mutate(action)}>
              {decide.isPending ? "Saving…" : `Yes, ${ACTION_TEXT[action].button.toLowerCase()}`}
            </button>
          )}
        </div>
      </Dialog>
    </CommentBox>
  );
}

function RespondPanel({ leave }: { leave: Leave }) {
  const me = useMe();
  const toast = useToast();
  const after = useAfterChange(leave);
  const [comment, setComment] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [problem, setProblem] = useState<string | null>(null);

  const respond = useMutation({
    mutationFn: () => api.postWithFiles<Leave>(`/leaves/${leave.id}/respond`, { comment: comment.trim() || null, version: leave.version }, files),
    onSuccess: (fresh) => {
      after(fresh);
      setComment("");
      setFiles([]);
      toast("Thanks! Your reply was sent.");
    },
    onError: (e) => {
      const msg = e instanceof ApiError ? (e.fields.comment ?? e.message) : "Something went wrong.";
      setProblem(msg);
      toast(msg, "error");
    },
  });

  return (
    <CommentBox title="Reply to the question" tone="info">
      <div>
        <label htmlFor="reply" className="sr-only">Your reply</label>
        <textarea id="reply" rows={3} maxLength={1000} className="input" placeholder="Write your reply…" value={comment} onChange={(e) => { setComment(e.target.value); setProblem(null); }} />
        <FieldError message={problem ?? undefined} />
      </div>
      <FileDrop files={files} onChange={setFiles} maxFiles={me.app.maxUploadFiles} maxMb={me.app.maxUploadMb} />
      <button type="button" className="btn-primary" disabled={respond.isPending} onClick={() => respond.mutate()}>
        {respond.isPending ? "Sending…" : "Send reply"}
      </button>
    </CommentBox>
  );
}

function CancelPanel({ leave }: { leave: Leave }) {
  const toast = useToast();
  const after = useAfterChange(leave);
  const [open, setOpen] = useState(false);
  const cancel = useMutation({
    mutationFn: () => api.post<Leave>(`/leaves/${leave.id}/cancel`, { version: leave.version }),
    onSuccess: (fresh) => { after(fresh); setOpen(false); toast("Request cancelled."); },
    onError: (e) => { setOpen(false); toast(e instanceof ApiError ? e.message : "Something went wrong.", "error"); },
  });
  return (
    <div>
      <button type="button" className="btn-secondary w-full text-danger-fg" onClick={() => setOpen(true)}>Cancel request</button>
      <Dialog open={open} title="Cancel this request?" onClose={() => setOpen(false)}>
        <p className="text-sm text-muted">Your approver will no longer see it. You can apply again afterwards.</p>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn-subtle" onClick={() => setOpen(false)}>Keep it</button>
          <button type="button" className="btn-danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            {cancel.isPending ? "Cancelling…" : "Yes, cancel"}
          </button>
        </div>
      </Dialog>
    </div>
  );
}
