import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/shared/lib/api";

import { useManifestStore } from "./useManifestStore";

const manifest = (seasons: number[]) => ({
  schema_version: 1,
  built_at: "2026-11-04T12:00:00+00:00",
  nflreadpy_version: "0.1.0",
  seasons: seasons.map((season) => ({
    season,
    path: `nfl_pbp_${season}.parquet`,
    rows: 1,
    max_week: 9,
    has_participation: true,
  })),
  player_index: null,
});

beforeEach(() => {
  vi.restoreAllMocks();
  useManifestStore.setState({ manifest: null, seasons: [], status: "idle", error: null });
});

describe("useManifestStore", () => {
  it("starts idle with no seasons", () => {
    expect(useManifestStore.getState()).toMatchObject({ status: "idle", seasons: [] });
  });

  it("loads the manifest and exposes its seasons in order", async () => {
    vi.spyOn(api, "fetchManifest").mockResolvedValue(manifest([2026, 2025]));

    await useManifestStore.getState().load();

    const state = useManifestStore.getState();
    expect(state.status).toBe("ready");
    expect(state.seasons).toEqual([2025, 2026]);
    expect(state.error).toBeNull();
  });

  it("keeps the error message when loading fails", async () => {
    vi.spyOn(api, "fetchManifest").mockRejectedValue(new Error("No data manifest found."));

    await useManifestStore.getState().load();

    const state = useManifestStore.getState();
    expect(state.status).toBe("error");
    expect(state.error).toBe("No data manifest found.");
    expect(state.seasons).toEqual([]);
  });
});
