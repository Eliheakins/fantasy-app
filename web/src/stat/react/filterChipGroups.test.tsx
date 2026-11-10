import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { useFilterChipGroups } from "./filterChipGroups";
import { ManifestContext } from "./manifest";

const withSeasons =
  (seasons: number[]) =>
  ({ children }: { children: ReactNode }) => (
    <ManifestContext.Provider value={{ manifest: null, seasons }}>{children}</ManifestContext.Provider>
  );

const seasonIds = (seasons: number[]) =>
  renderHook(() => useFilterChipGroups(), { wrapper: withSeasons(seasons) })
    .result.current.find((g) => g.id === "season")
    ?.options.map((o) => o.id) ?? [];

describe("useFilterChipGroups", () => {
  it("follows the seasons in the manifest", () => {
    expect(seasonIds([2030])).toEqual(["season-2030"]);
  });

  it("has no season group before the manifest has loaded", () => {
    expect(seasonIds([])).toEqual([]);
  });
});
