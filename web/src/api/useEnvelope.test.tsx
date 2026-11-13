import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { TeamContext, type TeamContextValue } from "@/lib/teamContext";
import { okReply, stubApi } from "@/test/fakeApi";
import { testQueryClient } from "@/test/render";
import { useEnvelopeMutation, useEnvelopeQuery } from "./useEnvelope";

const VIEWING_3: TeamContextValue = {
  team: 3,
  league: "a",
  teams: [],
  viewed: null,
  setTeam: () => {},
  notice: null,
  dismissNotice: () => {},
};

describe("useEnvelopeQuery", () => {
  it("keys and fetches the resolved url, with the viewed team last", async () => {
    const calls = stubApi(() => okReply([]));
    const client = testQueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <TeamContext.Provider value={VIEWING_3}>{children}</TeamContext.Provider>
      </QueryClientProvider>
    );
    const { result } = renderHook(() => useEnvelopeQuery("/api/leagues/{league}/lineup", { path: { league: "a" }, query: { week: 2 } }), {
      wrapper,
    });
    await waitFor(() => expect(result.current.kind).toBe("ready"));
    expect(calls.map((c) => c.url)).toEqual(["/api/leagues/a/lineup?week=2&team=3"]);
    expect(client.getQueryData(["api", "/api/leagues/a/lineup?week=2&team=3"])).toBeDefined();
  });
});

describe("useEnvelopeMutation", () => {
  it("invalidates api queries but leaves kept POST results alone", async () => {
    stubApi(() => okReply({ player_rows: 1 }));
    const client = testQueryClient();
    client.setQueryData(["api", "/api/leagues"], 1);
    client.setQueryData(["post", "find-trades", "L"], 2);
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useEnvelopeMutation("post", "/api/live/refresh", [["api"]]), { wrapper });
    result.current.mutate({});
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryState(["api", "/api/leagues"])?.isInvalidated).toBe(true);
    expect(client.getQueryState(["post", "find-trades", "L"])?.isInvalidated).toBe(false);
  });

  it("sends the method, params and body, and refetches only the keys it names", async () => {
    const calls = stubApi(() => okReply({ league_id: "L1", roster_id: 3 }));
    const client = testQueryClient();
    client.setQueryData(["api", "/api/me/leagues"], 1);
    client.setQueryData(["api", "/api/leagues"], 1);
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useEnvelopeMutation("put", "/api/me/leagues/{league_id}/team", [["api", "/api/me/leagues"]]), {
      wrapper,
    });
    result.current.mutate({ params: { path: { league_id: "L1" } }, body: { roster_id: 3 } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls).toEqual([{ url: "/api/me/leagues/L1/team", method: "PUT", body: { roster_id: 3 } }]);
    expect(client.getQueryState(["api", "/api/me/leagues"])?.isInvalidated).toBe(true);
    expect(client.getQueryState(["api", "/api/leagues"])?.isInvalidated).toBe(false);
  });

  it("fails with the server's message, and a network failure with the plain sentence", async () => {
    stubApi(() => ({
      status: 409,
      body: { status: "error", data: null, error: { code: "full", message: "You have 2 leagues." }, started_at: null },
    }));
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={testQueryClient()}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useEnvelopeMutation("post", "/api/admin/refresh"), { wrapper });
    result.current.mutate({});
    await waitFor(() => expect(result.current.error?.message).toBe("You have 2 leagues."));
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    result.current.mutate({});
    await waitFor(() => expect(result.current.error?.message).toMatch(/Could not reach the server/));
  });
});
