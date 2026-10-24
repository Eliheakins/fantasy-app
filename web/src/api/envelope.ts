import { ENVELOPE_STATUSES, type Envelope, type EnvelopeStatus } from "./types";

export const POLL_INTERVAL_MS = 2000;

export type ApiError = { message: string; code: string | null };

export type ApiState<T> =
  | { kind: "loading" }
  | { kind: "running"; startedAt: string | null }
  | { kind: "no_data"; message: string }
  | { kind: "error"; error: ApiError }
  | { kind: "ready"; data: T };

export class ApiFailure extends Error {
  readonly code: string | null;
  constructor(message: string, code: string | null = null) {
    super(message);
    this.code = code;
  }
}

/** Pure state machine: what the UI shows for the query's current envelope or failure. */
export function resolveState<T>(
  envelope: Envelope<T> | undefined,
  failure: Error | null,
): ApiState<T> {
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
    return error.code === "no_data"
      ? { kind: "no_data", message: error.message }
      : { kind: "error", error };
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
  if (
    typeof body !== "object" ||
    body === null ||
    !("status" in body) ||
    !ENVELOPE_STATUSES.includes(body.status as EnvelopeStatus)
  ) {
    throw new ApiFailure(`Unexpected response from ${url}`);
  }
  return body as Envelope<T>;
}
