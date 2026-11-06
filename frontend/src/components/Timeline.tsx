import { Ban, CircleCheck, CircleHelp, CircleX, MessageSquareReply, Send } from "lucide-react";
import { formatDateTime, statusLabel, timeAgo } from "../lib/format";
import type { Decision } from "../lib/types";
import { Avatar } from "./ui";

const VERB: Record<Decision["action"], string> = {
  SUBMIT: "submitted this request",
  APPROVE: "approved",
  REJECT: "rejected this request",
  REQUEST_INFO: "asked for more information",
  RESPOND: "replied",
  CANCEL: "cancelled this request",
};

const ICON: Record<Decision["action"], { Icon: typeof Send; cls: string }> = {
  SUBMIT: { Icon: Send, cls: "bg-selected text-link" },
  APPROVE: { Icon: CircleCheck, cls: "bg-success-bg text-success-fg" },
  REJECT: { Icon: CircleX, cls: "bg-danger-bg text-danger-fg" },
  REQUEST_INFO: { Icon: CircleHelp, cls: "bg-info-bg text-info-fg" },
  RESPOND: { Icon: MessageSquareReply, cls: "bg-selected text-link" },
  CANCEL: { Icon: Ban, cls: "bg-neutral-bg text-neutral-fg" },
};

const HEADER: Record<Decision["action"], string> = {
  SUBMIT: "bg-sunken",
  APPROVE: "bg-success-bg text-success-fg",
  REJECT: "bg-danger-bg text-danger-fg",
  REQUEST_INFO: "bg-info-bg text-info-fg",
  RESPOND: "bg-sunken",
  CANCEL: "bg-sunken",
};

/** GitHub-style activity feed: avatar, a connecting line, and a comment box when there is text. */
export function Timeline({ decisions }: { decisions: Decision[] }) {
  return (
    <ol className="relative space-y-4">
      <span aria-hidden="true" className="absolute top-2 bottom-2 left-4 w-0.5 bg-border" />
      {decisions.map((d) => {
        const { Icon, cls } = ICON[d.action];
        return (
          <li key={d.id} className="relative flex gap-3">
            <span className="relative z-10 ring-4 ring-bg"><Avatar name={d.actorName} size="md" /></span>
            <div className="min-w-0 flex-1">
              {d.comment ? (
                <div className="overflow-hidden rounded-md border border-border bg-surface">
                  <div className={`flex flex-wrap items-center gap-x-1.5 px-3 py-2 text-sm ${HEADER[d.action]}`}>
                    <Icon className="size-4 shrink-0" aria-hidden="true" />
                    <span className="font-semibold">{d.actorName}</span>
                    <span className="opacity-80">{VERB[d.action]}</span>
                    {d.action === "APPROVE" && d.toStatus === "PENDING_HOD" && <span className="opacity-80">(step 1 of 2)</span>}
                    <time className="ml-auto text-xs opacity-70" dateTime={d.createdAt} title={formatDateTime(d.createdAt)}>
                      {timeAgo(d.createdAt)}
                    </time>
                  </div>
                  <p className="px-3 py-2.5 text-sm whitespace-pre-wrap">{d.comment}</p>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-x-1.5 py-1.5 text-sm">
                  <span className={`grid size-5 place-items-center rounded-full ${cls}`}>
                    <Icon className="size-3" aria-hidden="true" />
                  </span>
                  <span className="font-semibold">{d.actorName}</span>
                  <span className="text-muted">{VERB[d.action]}</span>
                  {d.action === "APPROVE" && d.toStatus === "PENDING_HOD" && <span className="text-muted">(step 1 of 2)</span>}
                  <time className="text-xs text-muted" dateTime={d.createdAt} title={formatDateTime(d.createdAt)}>
                    · {timeAgo(d.createdAt)}
                  </time>
                </div>
              )}
              {d.fromStatus && (
                <p className="mt-1 text-xs text-muted">
                  {statusLabel[d.fromStatus]} → {statusLabel[d.toStatus]}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
