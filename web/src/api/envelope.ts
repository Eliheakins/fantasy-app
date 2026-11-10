import { ENVELOPE_STATUSES, type Envelope, type EnvelopeStatus } from "./types";

const POLL_INTERVAL_MS = 2000;
/** Fired when any request is refused because nobody is signed in (the session ended); the app then checks the session again. */
export const UNAUTHORIZED_EVENT = "fantasy:unauthorized";

export type ApiError = { message: string; code: string | null };

export type ApiState<T> =
  | { kind: "loading" }
  | { kind: "running"; startedAt: string | null }
  | { kind: "no_data"; message: string }
  | { kind: "error"; error: ApiError; retry?: () => void }
  | { kind: "ready"; data: T };

export class ApiFailure extends Error {
  readonly code: string | null;
  constructor(message: string, code: string | null = null) {
    super(message);
    this.code = code;
  }
}

/** Pure state machine: what the UI shows for the query's current envelope or failure. */
export function resolveState<T>(envelope: Envelope<T> | undefined, failure: Error | null): ApiState<T> {
  if (failure) {
    const code = failure instanceof ApiFailure ? failure.code : null;
    return code === "no_data"
      ? { kind: "no_data", message: failure.message }
      : { kind: "error", error: { message: failure.message, code } };
  }
  if (!envelope) return { kind: "loading" };
  if (envelope.status === "running") {
    return { kind: "running", startedAt: envelope.started_at };
  }
  if (envelope.status === "error") {
    const error: ApiError = envelope.error
      ? { message: envelope.error.message, code: envelope.error.code }
      : { message: "Unknown error", code: null };
    return error.code === "no_data" ? { kind: "no_data", message: error.message } : { kind: "error", error };
  }
  if (envelope.data === null) return { kind: "error", error: { message: "Response had no data", code: null } };
  return { kind: "ready", data: envelope.data };
}

/** Poll every 2 seconds while the job runs, never otherwise. */
export function pollInterval(envelope: Envelope<unknown> | undefined): number | false {
  return envelope?.status === "running" ? POLL_INTERVAL_MS : false;
}

export function elapsedSeconds(startedAt: string | null, now: number): number | null {
  if (startedAt === null) return null;
  const started = Date.parse(startedAt);
  return Number.isNaN(started) ? null : Math.max(0, Math.floor((now - started) / 1000));
}

/** The `error.code` of an envelope-shaped body, or null. */
function errorCode(body: unknown): string | null {
  const error = (body as { error?: unknown } | null)?.error;
  const code = (error as { code?: unknown } | null)?.code;
  return typeof code === "string" ? code : null;
}

/** The `error.message` of an envelope-shaped body, or null. */
function errorMessage(body: unknown): string | null {
  const error = (body as { error?: unknown } | null)?.error;
  const message = (error as { message?: unknown } | null)?.message;
  return typeof message === "string" ? message : null;
}

export async function fetchEnvelope<T>(url: string, init?: RequestInit): Promise<Envelope<T>> {
  // the server rejects non-GET requests without this header (blocks cross-site POSTs)
  const headers = { ...init?.headers, "X-Requested-With": "fantasy-app" };
  const response = await fetch(url, { ...init, headers });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiFailure(`Server returned HTTP ${response.status} without JSON`);
  }
  if (typeof body !== "object" || body === null || !("status" in body) || !ENVELOPE_STATUSES.includes(body.status as EnvelopeStatus)) {
    throw new ApiFailure(errorMessage(body) ?? `Unexpected response from ${url}`);
  }
  // the sign-in routes answer "unauthorized" for their own reasons; anything else means the session is gone
  if (errorCode(body) === "unauthorized" && !url.startsWith("/api/auth/") && typeof window !== "undefined") {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  return body as Envelope<T>;
}

export type Sent<T> = { ok: true; data: T } | { ok: false; error: ApiError };

const UNREACHABLE: ApiError = { message: "Could not reach the server. Try again.", code: null };

/** POST or DELETE with a JSON body and fold every way it can fail into one result: a refusal from
 * the server keeps its message, and a network failure becomes a plain sentence. Never throws. */
export async function sendJson<T>(url: string, method: "POST" | "PUT" | "DELETE", body?: unknown): Promise<Sent<T>> {
  try {
    const envelope = await fetchEnvelope<T>(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (envelope.status === "ok") return { ok: true, data: envelope.data as T };
    return { ok: false, error: envelope.error ?? { message: "Unknown error", code: null } };
  } catch (err) {
    // A non-JSON 5xx or an unexpected shape is not a network failure, so keep its message.
    return { ok: false, error: err instanceof ApiFailure ? { message: err.message, code: err.code } : UNREACHABLE };
  }
}
