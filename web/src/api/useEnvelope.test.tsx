import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { useEnvelopeMutation } from "./useEnvelope";

afterEach(() => vi.unstubAllGlobals());

describe("useEnvelopeMutation", () => {
  it("invalidates api queries but leaves kept POST results alone", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ status: "ok", data: { player_rows: 1 }, error: null, started_at: null })));
    const client = new QueryClient();
    client.setQueryData(["api", "/api/leagues"], 1);
    client.setQueryData(["post", "find-trades", "L"], 2);
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useEnvelopeMutation("/api/live/refresh"), { wrapper });
    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryState(["api", "/api/leagues"])?.isInvalidated).toBe(true);
    expect(client.getQueryState(["post", "find-trades", "L"])?.isInvalidated).toBe(false);
  });
});
