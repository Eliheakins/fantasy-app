import { errorReply, okReply, stubApi, stubScoped, takeUnexpected } from "./fakeApi";

describe("stubApi", () => {
  it("reads url, method and JSON body from a Request, as openapi-fetch sends one", async () => {
    const calls = stubApi(() => okReply(1));
    await fetch(new Request(`${window.location.origin}/api/me/leagues?x=1`, { method: "POST", body: JSON.stringify({ a: 1 }) }));
    expect(calls).toEqual([{ url: "/api/me/leagues?x=1", method: "POST", body: { a: 1 } }]);
  });

  it("records a request the test did not answer, and answers it with an error", async () => {
    stubApi((call) => (call.url === "/api/status" ? okReply({}) : undefined));
    const response = await fetch("/api/leagues");
    expect(response.status).toBe(500);
    expect(takeUnexpected()).toEqual(["GET /api/leagues"]);
    expect(takeUnexpected()).toEqual([]);
  });
});

describe("stubScoped", () => {
  it("answers the prefix and the app shell's own urls, and records anything else", async () => {
    const calls = stubScoped("/api/admin/", () => errorReply("x", "y"));
    await fetch("/api/admin/accounts");
    expect(await (await fetch("/api/leagues")).json()).toMatchObject({ status: "ok", data: [] });
    await fetch("/api/leagues/a/roster");
    expect(calls.map((c) => c.url)).toEqual(["/api/admin/accounts", "/api/leagues", "/api/leagues/a/roster"]);
    expect(takeUnexpected()).toEqual(["GET /api/leagues/a/roster"]);
  });
});
