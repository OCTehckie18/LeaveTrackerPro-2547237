import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

/** Native <dialog>: focus trap, Esc to close and inert background come from the browser. */
export function Dialog({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="dialog-title"
      className="m-auto w-[min(92vw,28rem)] rounded-xl border border-border bg-surface p-0 shadow-xl"
    >
      <div className="p-5">
        <h2 id="dialog-title" className="text-lg font-bold">
          {title}
        </h2>
        <div className="mt-3">{children}</div>
      </div>
    </dialog>
  );
}
