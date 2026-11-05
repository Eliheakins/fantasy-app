import { afterEach, describe, expect, it } from "vitest";

import { useManifestStore } from "@/stores/useManifestStore";
import { FIXTURE_SEASONS } from "@/test/seasons";

import { getFilterChipGroups } from "./filterChipGroups";

const seasonIds = () =>
  getFilterChipGroups()
    .find((g) => g.id === "season")
    ?.options.map((o) => o.id) ?? [];

afterEach(() => {
  useManifestStore.setState({ seasons: FIXTURE_SEASONS });
});

describe("getFilterChipGroups", () => {
  it("follows the seasons in the manifest store", () => {
    useManifestStore.setState({ seasons: [2030] });

    expect(seasonIds()).toEqual(["season-2030"]);
  });

  it("has no season group before the manifest has loaded", () => {
    useManifestStore.setState({ seasons: [] });

    expect(seasonIds()).toEqual([]);
  });
});
