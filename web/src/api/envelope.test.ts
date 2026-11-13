import { ApiFailure, elapsedSeconds, fetchEnvelope, pollInterval, resolveState, sendJson } from "./envelope";
import type { Envelope } from "./types";

const ok: Envelope<number> = { status: "ok", data: 7, error: null, started_at: null };
const running: Envelope<number> = {
  status: "running",
  data: null,
  error: null,
  started_at: "2026-10-24T12:00:00Z",
};

describe("resolveState", () => {
  it("is loading with nothing yet", () => {
    expect(resolveState(undefined, null)).toEqual({ kind: "loading" });
  });
  it("is ready with data on ok", () => {
    expect(resolveState(ok, null)).toEqual({ kind: "ready", data: 7 });
  });
  it("is running with the start time", () => {
    expect(resolveState(running, null)).toEqual({ kind: "running", startedAt: "2026-10-24T12:00:00Z" });
    expect(resolveState({ ...running, started_at: null }, null)).toEqual({
      kind: "running",
      startedAt: null,
    });
  });
  it("maps the no_data code to its own state", () => {
    const env: Envelope<number> = {
      status: "error",
      data: null,
      error: { message: "none", code: "no_data" },
      started_at: null,
    };
    expect(resolveState(env, null)).toEqual({ kind: "no_data", message: "none" });
  });
  it("keeps the invalid error code", () => {
    const env: Envelope<number> = {
      status: "error",
      data: null,
      error: { message: "bad", code: "invalid" },
      started_at: null,
    };
    expect(resolveState(env, null)).toEqual({ kind: "error", error: { message: "bad", code: "invalid" } });
  });
  it("turns a thrown failure into an error state", () => {
    expect(resolveState(undefined, new Error("net"))).toEqual({ kind: "error", error: { message: "net", code: null } });
    expect(resolveState(undefined, new ApiFailure("gone", "no_data")).kind).toBe("no_data");
  });
  it("goes running to ready when the poll returns ok", () => {
    expect(resolveState(running, null).kind).toBe("running");
    expect(resolveState(ok, null).kind).toBe("ready");
  });
});

describe("pollInterval", () => {
  it("polls every 2 seconds only while running", () => {
    expect(pollInterval(running)).toBe(2000);
    expect(pollInterval(ok)).toBe(false);
    expect(pollInterval(undefined)).toBe(false);
  });
});

describe("elapsedSeconds", () => {
  it("counts whole seconds since start and never goes negative", () => {
    const start = "2026-10-24T12:00:00Z";
    expect(elapsedSeconds(start, Date.parse(start) + 5900)).toBe(5);
    expect(elapsedSeconds(start, Date.parse(start) - 5000)).toBe(0);
    expect(elapsedSeconds(null, 0)).toBeNull();
    expect(elapsedSeconds("nope", 0)).toBeNull();
  });
});

describe("fetchEnvelope", () => {
  const stub = (body: unknown, status = 200) => vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(body, { status })));

  it("returns a well-formed envelope", async () => {
    stub({ status: "ok", data: 1, error: null, started_at: null });
    await expect(fetchEnvelope("get", "/api/status")).resolves.toMatchObject({ status: "ok", data: 1 });
  });
  it("rejects an unknown status literal", async () => {
    stub({ status: "weird", data: 1, error: null, started_at: null });
    await expect(fetchEnvelope("get", "/api/status")).rejects.toThrow("Unexpected response from /api/status");
  });
  it("rejects an ok envelope with no data key rather than handing on undefined", async () => {
    stub({ status: "ok", error: null, started_at: null });
    await expect(fetchEnvelope("get", "/api/status")).rejects.toThrow(new ApiFailure("Unexpected response from /api/status"));
  });
  it("rejects an envelope whose error is not {code, message}", async () => {
    stub({ status: "error", data: null, error: "boom", started_at: null });
    await expect(fetchEnvelope("get", "/api/status")).rejects.toThrow("Unexpected response from /api/status");
  });
  it("returns an error envelope sent with a non-2xx status", async () => {
    stub({ status: "error", data: null, error: { code: "invalid", message: "week: too big" }, started_at: null }, 422);
    const env = await fetchEnvelope("get", "/api/status");
    expect(resolveState(env, null)).toEqual({ kind: "error", error: { message: "week: too big", code: "invalid" } });
  });
  it("surfaces error.message from a body that has no status", async () => {
    stub({ error: { code: "server", message: "Something went wrong" } });
    await expect(fetchEnvelope("get", "/api/status")).rejects.toThrow("Something went wrong");
  });
  it("says a body that is not JSON is not JSON, ok or not", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>", { status: 502 })));
    await expect(fetchEnvelope("get", "/api/status")).rejects.toThrow("Server returned HTTP 502 without JSON");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>", { status: 200 })));
    await expect(fetchEnvelope("get", "/api/status")).rejects.toThrow("Server returned HTTP 200 without JSON");
  });
});

describe("sendJson", () => {
  it("a server reply that is not an envelope keeps its own message, not the network one", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({}, { status: 502 })));
    const sent = await sendJson("post", "/api/auth/logout");
    expect(sent).toMatchObject({ ok: false });
    expect(sent.ok === false && sent.error.message).not.toMatch(/Could not reach the server/);
  });

  it("a network failure becomes the plain sentence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const sent = await sendJson("post", "/api/auth/logout");
    expect(sent.ok === false && sent.error.message).toMatch(/Could not reach the server/);
  });
});
