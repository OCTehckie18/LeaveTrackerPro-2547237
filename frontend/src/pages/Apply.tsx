import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, CircleCheck, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { FileDrop } from "../components/FileDrop";
import { useToast } from "../components/Toast";
import { FieldError, PageHeader, Skeleton } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { useMe } from "../lib/auth";
import { formatDate, formatWeekday, leaveTypeLabel } from "../lib/format";
import type { LeaveDetail, LeaveType, Preview } from "../lib/types";

const schema = z
  .object({
    leaveType: z.enum(["ANNUAL", "SICK", "CASUAL", "OTHER"]),
    fromDate: z.string().min(1, "Please pick a start date."),
    toDate: z.string().min(1, "Please pick an end date."),
    reason: z
      .string()
      .trim()
      .min(10, "Please describe the reason (10–500 characters).")
      .max(500, "Please describe the reason (10–500 characters)."),
  })
  .refine((v) => !v.fromDate || !v.toDate || v.toDate >= v.fromDate, {
    path: ["toDate"],
    message: "End date must be on or after the start date.",
  });
type Values = z.infer<typeof schema>;

export default function Apply() {
  const me = useMe();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [files, setFiles] = useState<File[]>([]);
  const {
    register,
    handleSubmit,
    watch,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: { leaveType: "ANNUAL", fromDate: "", toDate: "", reason: "" },
  });

  const [from, to, reason] = watch(["fromDate", "toDate", "reason"]);
  const datesOk = Boolean(from && to && to >= from && from >= me.orgToday);

  const preview = useQuery({
    queryKey: ["preview", from, to],
    queryFn: () => api.post<Preview>("/leaves/preview", { fromDate: from, toDate: to }),
    enabled: datesOk,
    retry: false,
  });
  const p = preview.data;
  const previewError = preview.error instanceof ApiError ? preview.error : null;

  const blockers: string[] = [];
  if (p?.requiresDocuments && files.length === 0)
    blockers.push("Attach at least one supporting document (required for leave over 3 days).");
  if (p?.conflict) blockers.push(`You already have leave on these dates (LT-${p.conflict.id}).`);

  const submit = useMutation({
    mutationFn: (v: Values) => api.postWithFiles<LeaveDetail>("/leaves", v, files),
    onSuccess: (leave) => {
      qc.invalidateQueries({ queryKey: ["mine"] });
      qc.invalidateQueries({ queryKey: ["me"] });
      toast(`LT-${leave.id} submitted. ${leave.isExtended ? "It needs your Manager and then the HOD." : "Your manager has been notified."}`);
      nav(`/requests/${leave.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError) {
        const names: Record<string, keyof Values> = { fromDate: "fromDate", toDate: "toDate", reason: "reason", leaveType: "leaveType" };
        for (const [k, msg] of Object.entries(e.fields)) if (names[k]) setError(names[k], { message: msg });
        const extra = Object.entries(e.fields).filter(([k]) => !names[k]).map(([, m]) => m);
        toast(extra[0] ?? e.message, "error");
      }
    },
  });

  if (me.user.role === "HOD")
    return (
      <div className="card mx-auto max-w-md p-8 text-center">
        <h1 className="text-lg font-semibold">Heads of Department can't apply here</h1>
        <p className="mt-2 text-sm text-muted">There is no approver above the HOD in this system.</p>
      </div>
    );

  const chain = p?.approvalChain ?? (me.user.role === "MANAGER" ? ["HOD"] : ["Manager"]);

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Workspace" }, { label: "My requests", to: "/requests" }, { label: "New request" }]}
        title="Apply for leave"
        subtitle={`Filing as ${me.user.name}`}
      />
      <form noValidate className="grid items-start gap-6 lg:grid-cols-[1fr_320px]" onSubmit={handleSubmit((v) => submit.mutate(v))}>
        <div className="card space-y-5 p-4 md:p-6">
          <div>
            <label htmlFor="leaveType" className="label">Leave type</label>
            <select id="leaveType" className="input" {...register("leaveType")}>
              {(Object.keys(leaveTypeLabel) as LeaveType[]).map((t) => (
                <option key={t} value={t}>{leaveTypeLabel[t]}</option>
              ))}
            </select>
            <FieldError message={errors.leaveType?.message} />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="fromDate" className="label">From</label>
              <input id="fromDate" type="date" min={me.orgToday} className="input" {...register("fromDate")} />
              <FieldError message={errors.fromDate?.message ?? previewError?.fields.fromDate} />
            </div>
            <div>
              <label htmlFor="toDate" className="label">To</label>
              <input id="toDate" type="date" min={from || me.orgToday} className="input" {...register("toDate")} />
              <FieldError message={errors.toDate?.message ?? previewError?.fields.toDate} />
            </div>
          </div>
          {from && from < me.orgToday && !errors.fromDate && <FieldError message="Start date can't be in the past." />}
          {previewError && !previewError.fields.toDate && !previewError.fields.fromDate && <FieldError message={previewError.message} />}

          <div>
            <label htmlFor="reason" className="label">Reason</label>
            <textarea id="reason" rows={4} className="input" maxLength={500} aria-describedby="reason-count" placeholder="e.g. Family wedding out of town" {...register("reason")} />
            <div className="flex justify-between">
              <FieldError message={errors.reason?.message} />
              <span id="reason-count" className="mt-1 ml-auto text-xs text-muted">{reason.trim().length}/500</span>
            </div>
          </div>

          <FileDrop files={files} onChange={setFiles} maxFiles={me.app.maxUploadFiles} maxMb={me.app.maxUploadMb} required={p?.requiresDocuments} />

          <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-end">
            <Link to="/" className="btn-subtle">Cancel</Link>
            <button type="submit" className="btn-primary" disabled={submit.isPending || blockers.length > 0}>
              {submit.isPending ? "Submitting…" : "Submit request"}
            </button>
          </div>
          {blockers.map((b) => (
            <p key={b} className="-mt-2 text-right text-xs text-ext" role="status">{b}</p>
          ))}
        </div>

        {/* Live summary */}
        <aside className="space-y-4 lg:sticky lg:top-20" aria-label="Summary" aria-live="polite">
          <div className="card">
            <h2 className="border-b border-border px-4 py-2.5 text-sm font-semibold">Summary</h2>
            <div className="space-y-4 p-4">
              {preview.isFetching && datesOk ? (
                <div className="space-y-2"><Skeleton className="h-6 w-1/2" /><Skeleton className="h-4 w-3/4" /></div>
              ) : p ? (
                <div className="flex items-start gap-3">
                  <span className="grid size-10 shrink-0 place-items-center rounded-md bg-selected text-link">
                    <CalendarRange className="size-5" aria-hidden="true" />
                  </span>
                  <div>
                    <p className="text-lg leading-tight font-semibold">{p.days} day{p.days === 1 ? "" : "s"}</p>
                    <p className="text-xs text-muted">
                      {formatWeekday(from)} {formatDate(from)} → {formatWeekday(to)} {formatDate(to)}
                    </p>
                    {p.streak > p.days && <p className="mt-1 text-xs text-ext">Joins neighbouring leave: {p.streak} days in a row.</p>}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted">Pick your dates to see how many days this is and who needs to approve.</p>
              )}

              <div>
                <p className="mb-2 text-xs font-semibold text-muted">Approval path</p>
                <ol className="flex flex-wrap items-center gap-1.5 text-xs font-medium">
                  <li className="rounded-full bg-sunken px-2.5 py-1">You</li>
                  {chain.map((c) => (
                    <li key={c} className="flex items-center gap-1.5">
                      <span aria-hidden="true" className="text-muted">→</span>
                      <span className={`rounded-full px-2.5 py-1 ${c === "HOD" ? "bg-hod-bg text-hod-fg" : "bg-pending-bg text-pending-fg"}`}>{c}</span>
                    </li>
                  ))}
                  <li className="flex items-center gap-1.5">
                    <span aria-hidden="true" className="text-muted">→</span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-success-bg px-2.5 py-1 text-success-fg"><CircleCheck className="size-3" aria-hidden="true" />Approved</span>
                  </li>
                </ol>
              </div>

              {p?.isExtended && (
                <div role="status" className="flex gap-2.5 rounded-md border border-ext/30 bg-ext-bg p-3 text-ext">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                  <div className="text-xs">
                    <p className="font-bold">Extended leave · {p.streak} days in a row</p>
                    <p className="mt-0.5">Supporting documents are required and it needs your {p.approvalChain.join(" and then ")}.</p>
                  </div>
                </div>
              )}
              {p?.conflict && (
                <p className="field-error" role="alert">
                  You already have leave on these dates (LT-{p.conflict.id}: {formatDate(p.conflict.fromDate)} → {formatDate(p.conflict.toDate)}).
                </p>
              )}
            </div>
          </div>
        </aside>
      </form>
    </>
  );
}
