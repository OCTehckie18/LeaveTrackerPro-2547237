import { Check } from "lucide-react";
import { routeSteps } from "../lib/format";
import type { LeaveDetail } from "../lib/types";

/** Submitted → Manager → HOD → Done. Completed steps green; the current step takes the status colour. */
export function Stepper({ leave }: { leave: LeaveDetail }) {
  const approvers = routeSteps[leave.approverRoute];
  const steps = ["Submitted", ...approvers, "Done"];
  const stage = leave.status === "NEEDS_INFO" ? leave.resumeStatus : leave.status;

  let current: number;
  if (leave.status === "APPROVED") current = steps.length - 1;
  else if (stage === "PENDING_HOD") current = steps.indexOf("HOD");
  else if (stage === "PENDING_MANAGER") current = steps.indexOf("Manager");
  else {
    // REJECTED / CANCELLED: stopped at the last stage that acted
    const last = [...leave.decisions].reverse().find((d) => d.stage !== "EMPLOYEE");
    current = last ? steps.indexOf(last.stage === "HOD" ? "HOD" : "Manager") : 0;
  }
  const stopped = leave.status === "REJECTED" || leave.status === "CANCELLED";
  const currentCls =
    leave.status === "NEEDS_INFO"
      ? "bg-info-fg text-surface"
      : leave.status === "REJECTED"
        ? "bg-danger-fg text-surface"
        : leave.status === "CANCELLED"
          ? "bg-neutral-fg text-surface"
          : leave.status === "PENDING_HOD"
            ? "bg-hod-fg text-surface"
            : "bg-pending-fg text-surface";

  return (
    <ol className="flex items-center" aria-label="Approval progress">
      {steps.map((label, i) => {
        const done = leave.status === "APPROVED" ? true : i < current;
        const active = !done && i === current;
        return (
          <li key={label} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <span
                aria-current={active ? "step" : undefined}
                className={`grid size-8 place-items-center rounded-full text-xs font-bold ${
                  done ? "bg-success-fg text-surface" : active ? currentCls : "bg-neutral-bg text-neutral-fg"
                }`}
              >
                {done ? <Check className="size-4" aria-hidden="true" /> : i + 1}
              </span>
              <span className={`text-xs ${active ? "font-semibold" : "text-muted"}`}>{label}</span>
            </div>
            {i < steps.length - 1 && (
              <span
                aria-hidden="true"
                className={`mx-1 mb-5 h-0.5 flex-1 ${done && !(stopped && i >= current) ? "bg-success-fg" : "bg-border"}`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
