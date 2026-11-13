import { createAppQueryClient } from "./queryClient";

describe("createAppQueryClient", () => {
  const retryOf = (queryKey: readonly unknown[], own: { retry?: boolean | number } = {}) =>
    createAppQueryClient().defaultQueryOptions({ queryKey, ...own }).retry;

  it("retries an /api GET and a kept POST result once", () => {
    expect(retryOf(["api", "/api/leagues"])).toBe(1);
    expect(retryOf(["post", "trade", "/api/leagues/a/trade"])).toBe(1);
  });
  it("keeps react-query's default for every other query", () => {
    expect(retryOf(["search", null, "x"])).toBeUndefined(); // undefined: react-query's own default of 3
  });
  it("lets a query's own retry win", () => {
    expect(retryOf(["api", "/api/me"], { retry: false })).toBe(false);
  });
});
