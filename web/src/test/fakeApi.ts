import { vi } from "vitest";
import type { ApiState } from "@/api/envelope";

/**
 * A stand-in for the API in component tests: every call is recorded, and the test decides each answer.
 * Strict, like MSW's onUnhandledRequest "error": a request the test does not answer gets a 500 and is
 * recorded, and the global afterEach in `setup.ts` fails the test with "unexpected request: GET /api/...".
 */

export type Call = { url: string; method: string; body: unknown };
export type Reply = { status?: number; body: object };

export const okReply = (data: unknown): Reply => ({
  body: { status: "ok", data, error: null, started_at: null },
});

export const errorReply = (code: string, message: string, status = 200): Reply => ({
  status,
  body: { status: "error", data: null, error: { code, message }, started_at: null },
});

const unexpected: string[] = [];

/** The unanswered requests since the last call ("GET /api/..."), and forget them. */
export function takeUnexpected(): string[] {
  return unexpected.splice(0);
}

/** The url as the app wrote it ("/api/..."): openapi-fetch sends an absolute Request on the page's origin. */
function relative(url: string): string {
  const parsed = new URL(url, window.location.origin);
  return parsed.origin === window.location.origin ? `${parsed.pathname}${parsed.search}` : url;
}

async function readCall(input: RequestInfo | URL, init?: RequestInit): Promise<Call> {
  if (input instanceof Request) {
    const text = await input.text();
    return { url: relative(input.url), method: input.method, body: text ? JSON.parse(text) : undefined };
  }
  return { url: relative(String(input)), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined };
}

/** A stub's answer: a reply, a raw Response (a body that is not JSON), or undefined for a call the test does not
 * expect. Throwing makes the fetch fail as a network error does. */
type Answer = Reply | Response | undefined;

/** Replace `fetch`; returns the list that fills with each call as it happens. */
export function stubApi(answer: (call: Call) => Answer | Promise<Answer>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = await readCall(input, init);
      calls.push(call);
      const reply = await answer(call);
      if (reply instanceof Response) return reply;
      if (reply === undefined) {
        unexpected.push(`${call.method} ${call.url}`);
        return Response.json(errorReply("unexpected_request", `No stub for ${call.method} ${call.url}`).body, { status: 500 });
      }
      return Response.json(reply.body, { status: reply.status ?? 200 });
    }),
  );
  return calls;
}

/** `stubApi` over a table of response bodies keyed by path (the query string is ignored); any other path is unexpected. */
export function stubRoutes(routes: Readonly<Record<string, object>>): Call[] {
  return stubApi((call) => {
    const body = routes[call.url.split("?")[0] ?? call.url];
    return body === undefined ? undefined : { body };
  });
}

/** What the app shell fetches on its own (league list, data status, the account's leagues), answered empty. */
const SHELL: Readonly<Record<string, Reply>> = {
  "/api/leagues": okReply([]),
  "/api/status": okReply({}),
  "/api/me/leagues": okReply([]),
};

/** Like `stubApi`, but only urls under `prefix` get the test's answer; the app shell's own GETs (`SHELL`)
 * get an empty answer, so the part under test can be mounted inside its providers. Anything else is unexpected. */
export function stubScoped(prefix: string, answer: (call: Call) => Answer | Promise<Answer>): Call[] {
  return stubApi((call) => (call.url.startsWith(prefix) ? answer(call) : call.method === "GET" ? SHELL[call.url] : undefined));
}

/** The first element, or a failure that says so (indexing an empty array is a type error here). */
export function first<T>(items: readonly T[]): T {
  const [head] = items;
  if (head === undefined) throw new Error("expected at least one element");
  return head;
}

/** A league route and its query as the short path mocked `useLeagueApi` responders match on:
 * ("/api/leagues/{league}/waivers", { horizon: "playoffs" }) -> "waivers?horizon=playoffs". */
export function leaguePath(route: string, query?: object): string {
  const path = route.replace("/api/leagues/{league}/", "");
  const search = Object.entries(query ?? {})
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${k}=${String(v)}`)
    .join("&");
  return search ? `${path}?${search}` : path;
}

/** A mocked `useLeagueApi` responder that answers only the listed `leaguePath`s; any other route fails the test. */
export function onlyRoutes(table: Readonly<Record<string, ApiState<unknown>>>): (path: string) => ApiState<unknown> {
  return (path) => {
    const state = table[path];
    if (state === undefined) throw new Error(`unlisted route: ${path}`);
    return state;
  };
}
