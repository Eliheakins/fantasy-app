import { vi } from "vitest";

/** A stand-in for the API in component tests: every call is recorded, and the test decides each answer. */

export type Call = { url: string; method: string; body: unknown };
export type Reply = { status?: number; body: object };

export const okReply = (data: unknown): Reply => ({
  body: { status: "ok", data, error: null, started_at: null },
});

export const errorReply = (code: string, message: string, status = 200): Reply => ({
  status,
  body: { status: "error", data: null, error: { code, message }, started_at: null },
});

/** Replace `fetch`; returns the list that fills with each call as it happens. */
export function stubApi(answer: (call: Call) => Reply): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const call: Call = {
        url,
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      };
      calls.push(call);
      const reply = answer(call);
      return Response.json(reply.body, { status: reply.status ?? 200 });
    }),
  );
  return calls;
}

/** Like `stubApi`, but only urls under `prefix` get the test's answer; the app shell's own requests
 * (leagues, status) get an empty list, so the part under test can be mounted inside its providers. */
export function stubScoped(prefix: string, answer: (call: Call) => Reply): Call[] {
  return stubApi((call) => (call.url.startsWith(prefix) ? answer(call) : okReply([])));
}

/** The first element, or a failure that says so (indexing an empty array is a type error here). */
export function first<T>(items: readonly T[]): T {
  const [head] = items;
  if (head === undefined) throw new Error("expected at least one element");
  return head;
}
