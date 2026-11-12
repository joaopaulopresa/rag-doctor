/** Small client for the RAG Doctor API: JSON requests and server-sent events. */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
  }
}

function messageOf(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  if (Array.isArray(detail)) return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
  return `Request failed (${status})`;
}

export async function api<T>(path: string, options: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = options;
  const response = await fetch(path, {
    credentials: "same-origin",
    ...rest,
    headers: json !== undefined ? { "Content-Type": "application/json", ...headers } : headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = (await response.json()).detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(messageOf(detail, response.status), response.status, detail);
  }
  return (await response.json()) as T;
}

/** POST a JSON body and read the server-sent events of the response, one callback per event. */
export async function postStream(path: string, body: unknown, onEvent: (event: Record<string, unknown>) => void): Promise<void> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    let detail: unknown = null;
    try {
      detail = (await response.json()).detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(messageOf(detail, response.status), response.status, detail);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      for (const line of block.split("\n")) {
        if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)));
      }
    }
  }
}

export function pct(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? "–" : `${(100 * value).toFixed(digits)}%`;
}

export function usd(value: number | null | undefined, digits = 4): string {
  return value === null || value === undefined ? "–" : `$${value.toFixed(digits)}`;
}

/** A difference of shares as signed percentage points, for example "+16.7 pts". */
export function points(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "–";
  const n = 100 * value;
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)} pts`;
}
