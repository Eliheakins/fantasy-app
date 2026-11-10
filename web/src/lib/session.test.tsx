import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { errorReply, okReply, stubApi } from "@/test/fakeApi";
import { ME_KEY, redeemInvite, signIn, signOut, useSession } from "./session";

const ME = { email: "friend@example.com", is_admin: false, sleeper_user_id: null };

afterEach(() => vi.unstubAllGlobals());

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

describe("useSession", () => {
  it("is signed in when the server knows the caller", async () => {
    stubApi(() => okReply(ME));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSession(), { wrapper });
    expect(result.current.kind).toBe("loading");
    await waitFor(() => expect(result.current).toEqual({ kind: "signedIn", me: ME }));
  });

  it("is signed out when the server says unauthorized", async () => {
    stubApi(() => errorReply("unauthorized", "Sign in to continue.", 401));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.kind).toBe("signedOut"));
  });

  it("is an error, not signed out, when the server fails some other way", async () => {
    stubApi(() => errorReply("server", "Database is down", 500));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.kind).toBe("error"));
    expect(result.current).toMatchObject({ message: "Database is down" });
  });
});

describe("signIn", () => {
  it("posts the credentials, stores the account, and drops what the last person had cached", async () => {
    const calls = stubApi(() => okReply(ME));
    const { client } = setup();
    client.setQueryData(["api", "/api/leagues"], { status: "ok", data: ["someone else's league"] });

    const failure = await signIn(client, "friend@example.com", "a long enough password");

    expect(failure).toBeNull();
    expect(calls).toEqual([
      {
        url: "/api/auth/login",
        method: "POST",
        body: { email: "friend@example.com", password: "a long enough password" },
      },
    ]);
    expect(client.getQueryData(["api", "/api/leagues"])).toBeUndefined();
    expect(client.getQueryData(ME_KEY)).toMatchObject({ status: "ok", data: ME });
  });

  it("returns the server's message and leaves the cache alone on a wrong password", async () => {
    stubApi(() => errorReply("invalid", "Wrong email or password.", 401));
    const { client } = setup();
    client.setQueryData(["api", "/api/leagues"], "kept");
    const failure = await signIn(client, "friend@example.com", "nope nope nope");
    expect(failure).toEqual({ code: "invalid", message: "Wrong email or password." });
    expect(client.getQueryData(["api", "/api/leagues"])).toBe("kept");
  });

  it("explains a network failure instead of throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const { client } = setup();
    const failure = await signIn(client, "friend@example.com", "a long enough password");
    expect(failure?.message).toMatch(/could not reach the server/i);
  });
});

describe("redeemInvite", () => {
  it("posts the token and the new password and signs in", async () => {
    const calls = stubApi(() => okReply(ME));
    const { client } = setup();
    const failure = await redeemInvite(client, "t".repeat(30), "a long enough password");
    expect(failure).toBeNull();
    expect(calls[0]).toMatchObject({
      url: "/api/auth/redeem",
      body: { token: "t".repeat(30), password: "a long enough password" },
    });
    expect(client.getQueryData(ME_KEY)).toMatchObject({ data: ME });
  });

  it("passes on why the link failed", async () => {
    stubApi(() => errorReply("invalid", "This invite link was already used.", 400));
    const failure = await redeemInvite(setup().client, "t".repeat(30), "a long enough password");
    expect(failure?.message).toBe("This invite link was already used.");
  });
});

describe("signOut", () => {
  it("tells the server, forgets everything cached, and marks the session signed out", async () => {
    const calls = stubApi(() => okReply({ signed_out: true }));
    const { client } = setup();
    client.setQueryData(["api", "/api/leagues"], "private");
    client.setQueryData(ME_KEY, { status: "ok", data: ME });

    await signOut(client);

    expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual(["POST /api/auth/logout"]);
    expect(client.getQueryData(["api", "/api/leagues"])).toBeUndefined();
    expect(client.getQueryData(ME_KEY)).toMatchObject({ error: { code: "unauthorized" } });
  });
});

describe("browser storage follows the account", () => {
  const OWN = { "fantasy.league": "L1", "fantasy.lastVisit.L1": "{}", "fantasy.savedSearches": "[]", "bridge.askLog.v1": "[]", "bridge.intentCache.v1": "{}" };
  beforeEach(() => {
    window.localStorage.clear();
    for (const [key, value] of Object.entries(OWN)) window.localStorage.setItem(key, value);
    window.localStorage.setItem("theme", "dark");
  });
  afterEach(() => window.localStorage.clear());

  const keys = () => Object.keys(window.localStorage).sort();

  it("clears the fantasy.* and bridge.* keys when a different account signs in", async () => {
    window.localStorage.setItem("fantasy.account", "someone.else@example.com");
    stubApi(() => okReply(ME));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.kind).toBe("signedIn"));
    expect(keys()).toEqual(["fantasy.account", "theme"]);
    expect(window.localStorage.getItem("fantasy.account")).toBe(ME.email);
  });

  it("keeps them for the same account", async () => {
    window.localStorage.setItem("fantasy.account", ME.email);
    stubApi(() => okReply(ME));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.kind).toBe("signedIn"));
    expect(keys()).toEqual([...Object.keys(OWN), "fantasy.account", "theme"].sort());
  });

  it("keeps them on a browser that has no account stored yet", async () => {
    stubApi(() => okReply(ME));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.kind).toBe("signedIn"));
    expect(keys()).toEqual([...Object.keys(OWN), "fantasy.account", "theme"].sort());
    expect(window.localStorage.getItem("fantasy.account")).toBe(ME.email);
  });

  it("clears them when someone else signs in on the same browser", async () => {
    window.localStorage.setItem("fantasy.account", "someone.else@example.com");
    stubApi(() => okReply(ME));
    expect(await signIn(setup().client, ME.email, "a long enough password")).toBeNull();
    expect(keys()).toEqual(["fantasy.account", "theme"]);
  });

  it("still signs in when storage is blocked", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    stubApi(() => okReply(ME));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.kind).toBe("signedIn"));
    vi.restoreAllMocks();
  });
});
