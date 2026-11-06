/** Thin fetch wrapper: same-origin cookies, the API's friendly error envelope, and a network fallback. */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields: Record<string, string> = {},
    public requestId?: string,
  ) {
    super(message);
  }
}

const NETWORK_MESSAGE = "We couldn't reach the server. Your input is kept, please try again.";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { credentials: "same-origin", ...init });
  } catch {
    throw new ApiError(0, "NETWORK", NETWORK_MESSAGE);
  }
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body (e.g. a proxy error page) */
  }
  if (!res.ok) {
    const e = (data as { error?: { code?: string; message?: string; fields?: Record<string, string>; requestId?: string } } | null)?.error;
    throw new ApiError(
      res.status,
      e?.code ?? (res.status === 502 || res.status === 504 ? "SERVICE_UNAVAILABLE" : "INTERNAL"),
      e?.message ??
        (res.status === 502 || res.status === 504
          ? "The server is waking up. Please try again in a few seconds."
          : "Something went wrong on our side. Please try again."),
      e?.fields ?? {},
      e?.requestId,
    );
  }
  return data as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, json(body ?? {})),
  /** Leave (or reply) with documents: the JSON travels as the `data` part next to the files. */
  postWithFiles: <T>(path: string, data: unknown, files: File[]) => {
    if (files.length === 0) return request<T>(path, json(data));
    const form = new FormData();
    form.set("data", JSON.stringify(data));
    files.forEach((f) => form.append("files", f));
    return request<T>(path, { method: "POST", body: form });
  },
};

export const documentUrl = (leaveId: number, docId: string, inline = false) =>
  `/api/v1/leaves/${leaveId}/documents/${docId}?disposition=${inline ? "inline" : "attachment"}`;
