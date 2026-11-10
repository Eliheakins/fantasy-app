import { errorReply, okReply, stubApi } from "@/test/fakeApi";
import { fetchEnvelope, UNAUTHORIZED_EVENT } from "./envelope";

afterEach(() => vi.unstubAllGlobals());

function listen(): { count: () => number; stop: () => void } {
  let seen = 0;
  const handler = () => (seen += 1);
  window.addEventListener(UNAUTHORIZED_EVENT, handler);
  return { count: () => seen, stop: () => window.removeEventListener(UNAUTHORIZED_EVENT, handler) };
}

describe("fetchEnvelope and a session that ended", () => {
  it("announces an unauthorized answer from any data route", async () => {
    stubApi(() => errorReply("unauthorized", "Sign in to continue.", 401));
    const events = listen();
    await fetchEnvelope("/api/leagues");
    expect(events.count()).toBe(1);
    events.stop();
  });

  it("stays quiet for the sign-in routes themselves", async () => {
    stubApi(() => errorReply("unauthorized", "Sign in to continue.", 401));
    const events = listen();
    await fetchEnvelope("/api/auth/me");
    expect(events.count()).toBe(0);
    events.stop();
  });

  it("stays quiet for other errors and for good answers", async () => {
    const events = listen();
    stubApi(() => errorReply("busy", "Try again.", 429));
    await fetchEnvelope("/api/leagues");
    stubApi(() => okReply([]));
    await fetchEnvelope("/api/leagues");
    expect(events.count()).toBe(0);
    events.stop();
  });
});
