import { FileText, Paperclip, X } from "lucide-react";
import { useId, useRef, useState } from "react";
import { formatBytes } from "../lib/format";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx,application/pdf,image/png,image/jpeg";

/** Quick client-side checks for fast feedback; the server re-validates the real file content. */
export function FileDrop({
  files,
  onChange,
  maxFiles,
  maxMb,
  required,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  maxFiles: number;
  maxMb: number;
  required?: boolean;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<string | null>(null);

  function add(list: FileList | null) {
    if (!list) return;
    setProblem(null);
    const next = [...files];
    for (const f of Array.from(list)) {
      if (next.length >= maxFiles) {
        setProblem(`You can attach up to ${maxFiles} files.`);
        break;
      }
      if (f.size > maxMb * 1024 * 1024) {
        setProblem(`“${f.name}” is larger than ${maxMb} MB. Try a smaller photo or a PDF.`);
        continue;
      }
      if (!/\.(pdf|png|jpe?g|docx)$/i.test(f.name)) {
        setProblem(`“${f.name}” isn't supported. Please use a PDF, PNG, JPG or DOCX.`);
        continue;
      }
      next.push(f);
    }
    onChange(next);
    if (input.current) input.current.value = "";
  }

  return (
    <div>
      <label htmlFor={id} className="label">
        Supporting documents{" "}
        {required ? <span className="text-ext">(required)</span> : <span className="text-muted">(optional)</span>}
      </label>
      <label
        htmlFor={id}
        className="flex min-h-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-border bg-surface p-4 text-center text-muted hover:border-primary"
      >
        <Paperclip className="size-5" aria-hidden="true" />
        <span className="text-sm">
          Tap to choose files (PDF, PNG, JPG, DOCX · up to {maxFiles} files, {maxMb} MB each)
        </span>
      </label>
      <input
        id={id}
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        onChange={(e) => add(e.target.files)}
      />
      {problem && (
        <p className="field-error" role="alert">
          {problem}
        </p>
      )}
      {files.length > 0 && (
        <ul className="mt-2 space-y-2">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="card flex items-center gap-3 p-2 pl-3 text-sm">
              <FileText className="size-4 shrink-0 text-muted" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate">{f.name}</span>
              <span className="text-muted">{formatBytes(f.size)}</span>
              <button
                type="button"
                className="btn-secondary min-h-9 px-2"
                aria-label={`Remove ${f.name}`}
                onClick={() => onChange(files.filter((_, j) => j !== i))}
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
