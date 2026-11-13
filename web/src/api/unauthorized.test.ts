import { errorReply, okReply, stubApi } from "@/test/fakeApi";
import { fetchEnvelope, UNAUTHORIZED_EVENT } from "./envelope";

function listen(): { count: () => number; stop: () => void } {
  let seen = 0;
  const handler = () => (seen += 1);
  window.addEventListener(UNAUTHORIZED_EVENT, handler);
  return { count: () => seen, stop: () => window.removeEventListener(UNAUTHORIZED_EVENT, handler) };
}

describe("fetchEnvelope and a session that ended", () => {
  it("announces an unauthorized answer from any data route", async () => {
    stubApi((call) => (call.url === "/api/leagues" ? errorReply("unauthorized", "Sign in to continue.", 401) : undefined));
    const events = listen();
    await fetchEnvelope("get", "/api/leagues");
    expect(events.count()).toBe(1);
    events.stop();
  });

  it("stays quiet for the sign-in routes themselves", async () => {
    stubApi((call) => (call.url === "/api/auth/me" ? errorReply("unauthorized", "Sign in to continue.", 401) : undefined));
    const events = listen();
    await fetchEnvelope("get", "/api/auth/me");
    expect(events.count()).toBe(0);
    events.stop();
  });

  it("stays quiet for other errors and for good answers", async () => {
    const events = listen();
    stubApi((call) => (call.url === "/api/leagues" ? errorReply("busy", "Try again.", 429) : undefined));
    await fetchEnvelope("get", "/api/leagues");
    stubApi((call) => (call.url === "/api/leagues" ? okReply([]) : undefined));
    await fetchEnvelope("get", "/api/leagues");
    expect(events.count()).toBe(0);
    events.stop();
  });
});
