import { apiUrl } from "./client";
import { fetchEnvelope } from "./envelope";

const OK = { status: "ok", data: [], error: null, started_at: null };

/** The Request openapi-fetch handed to `fetch`. */
function stubFetch(): () => Request {
  const fn = vi.fn<(request: Request) => Promise<Response>>(async () => Response.json(OK));
  vi.stubGlobal("fetch", fn);
  return () => {
    const request = fn.mock.calls[0]?.[0];
    if (!(request instanceof Request)) throw new Error("fetch was not called with a Request");
    return request;
  };
}

describe("apiUrl", () => {
  it("fills path params and appends the query in order, encoded as before", () => {
    expect(apiUrl("/api/leagues/{league}/status-changes", { path: { league: "a b" }, query: { since: "2026-11-13T10:00:00+00:00" } })).toBe(
      "/api/leagues/a%20b/status-changes?since=2026-11-13T10%3A00%3A00%2B00%3A00",
    );
    expect(apiUrl("/api/leagues/{league}/player-weeks", { path: { league: "a" }, query: { gsis_id: "00-1", n: 4 } })).toBe(
      "/api/leagues/a/player-weeks?gsis_id=00-1&n=4",
    );
    expect(apiUrl("/api/status")).toBe("/api/status");
  });
});

describe("fetchEnvelope through the typed client", () => {
  it("GETs the resolved route on this origin with the app header", async () => {
    const sent = stubFetch();
    await fetchEnvelope("get", "/api/leagues/{league}/roster", { params: { path: { league: "a" } } });
    const request = sent();
    expect(request.method).toBe("GET");
    expect(request.url).toBe(`${window.location.origin}/api/leagues/a/roster`);
    expect(request.headers.get("X-Requested-With")).toBe("fantasy-app");
  });

  it("sends a typed JSON body with its content type", async () => {
    const sent = stubFetch();
    await fetchEnvelope("put", "/api/me/leagues/{league_id}/team", { params: { path: { league_id: "L1" } }, body: { roster_id: 3 } });
    const request = sent();
    expect(request.method).toBe("PUT");
    expect(request.url).toBe(`${window.location.origin}/api/me/leagues/L1/team`);
    expect(request.headers.get("Content-Type")).toBe("application/json");
    expect(await request.json()).toEqual({ roster_id: 3 });
  });
});
