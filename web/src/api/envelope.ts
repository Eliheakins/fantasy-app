import { type ApiData, api, apiUrl, type InitArg, type LooseParams, type Method, type Route } from "./client";
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

/** Still waiting: the request is in flight or the server is computing the answer. */
export const isPending = (s: ApiState<unknown>): boolean => s.kind === "loading" || s.kind === "running";

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

/** The `error.code` or `error.message` of an envelope-shaped body, or null. */
function errorField(body: unknown, key: "code" | "message"): string | null {
  const error = (body as { error?: Record<string, unknown> } | null)?.error;
  const value = error?.[key];
  return typeof value === "string" ? value : null;
}

type LooseInit = { params?: LooseParams; body?: unknown };

/** The body as sent: parsed JSON, or a failure that says the server sent something else. */
async function readBody(method: Method, route: string, { params, body }: LooseInit): Promise<unknown> {
  // "stream" leaves an ok body unread, so it is parsed below as before; openapi-fetch reads a non-2xx body
  // itself and hands back the parsed JSON, or the raw text when it was not JSON.
  const { response, error } = await api.request(method, route as never, { params, body, parseAs: "stream" } as never);
  const status: number = response.status;
  if (!response.ok) {
    if (typeof error === "string" || error === undefined) throw new ApiFailure(`Server returned HTTP ${status} without JSON`);
    return error;
  }
  try {
    return await response.json();
  } catch {
    throw new ApiFailure(`Server returned HTTP ${status} without JSON`);
  }
}

async function requestEnvelope<T>(method: Method, route: string, init: LooseInit = {}): Promise<Envelope<T>> {
  const body = await readBody(method, route, init);
  if (typeof body !== "object" || body === null || !("status" in body) || !ENVELOPE_STATUSES.includes(body.status as EnvelopeStatus)) {
    throw new ApiFailure(errorField(body, "message") ?? `Unexpected response from ${apiUrl(route, init.params)}`);
  }
  // the sign-in routes answer "unauthorized" for their own reasons; anything else means the session is gone
  if (errorField(body, "code") === "unauthorized" && !route.startsWith("/api/auth/") && typeof window !== "undefined") {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  return body as Envelope<T>;
}

/** One call to an envelope route: the route template plus its params and body, typed from the schema. */
export function fetchEnvelope<M extends Method, P extends Route<M>>(
  method: M,
  route: P,
  ...[init]: InitArg<P, M>
): Promise<Envelope<ApiData<P, M>>> {
  return requestEnvelope<ApiData<P, M>>(method, route, init as LooseInit | undefined);
}

/** The loose form of `fetchEnvelope`, for the react-query wrappers that pass a route through (`useEnvelope.ts`). */
export const fetchEnvelopeAt = requestEnvelope;

export type Sent<T> = { ok: true; data: T } | { ok: false; error: ApiError };

const UNREACHABLE: ApiError = { message: "Could not reach the server. Try again.", code: null };

/** An ok envelope's data; otherwise an ApiFailure with the server's message, or the plain sentence for a network failure. */
export async function sendEnvelope<T>(method: Method, route: string, init: LooseInit = {}): Promise<T> {
  let envelope: Envelope<T>;
  try {
    envelope = await requestEnvelope<T>(method, route, init);
  } catch (err) {
    // A non-JSON 5xx or an unexpected shape is not a network failure, so keep its message.
    throw err instanceof ApiFailure ? err : new ApiFailure(UNREACHABLE.message);
  }
  if (envelope.status !== "ok") {
    const error = envelope.error ?? { message: "Unknown error", code: null };
    throw new ApiFailure(error.message, error.code);
  }
  return envelope.data as T;
}

/** Send a write and fold every way it can fail into one result: a refusal from the server keeps its message,
 * and a network failure becomes a plain sentence. Never throws. For session.tsx; components use `useEnvelopeMutation`. */
export async function sendJson<M extends Method, P extends Route<M>>(
  method: M,
  route: P,
  ...[init]: InitArg<P, M>
): Promise<Sent<ApiData<P, M>>> {
  try {
    return { ok: true, data: await sendEnvelope<ApiData<P, M>>(method, route, init as LooseInit | undefined) };
  } catch (err) {
    const failure = err instanceof ApiFailure ? err : new ApiFailure(UNREACHABLE.message);
    return { ok: false, error: { message: failure.message, code: failure.code } };
  }
}
