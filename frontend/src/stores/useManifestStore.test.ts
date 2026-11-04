import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/shared/lib/api";

import { useManifestStore } from "./useManifestStore";

const manifest = (seasons: number[]) => ({
  schema_version: 1 as const,
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
  player_game: null,
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

  it("does not fetch twice when load is called while already loading or after it is ready", async () => {
    const fetchSpy = vi.spyOn(api, "fetchManifest").mockResolvedValue(manifest([2025]));

    await Promise.all([useManifestStore.getState().load(), useManifestStore.getState().load()]);
    await useManifestStore.getState().load();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("tries again after an error", async () => {
    const fetchSpy = vi
      .spyOn(api, "fetchManifest")
      .mockRejectedValueOnce(new Error("down"))
      .mockResolvedValueOnce(manifest([2025]));

    await useManifestStore.getState().load();
    await useManifestStore.getState().load();

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(useManifestStore.getState().status).toBe("ready");
  });

  it("lists each season once even if the manifest repeats one", async () => {
    vi.spyOn(api, "fetchManifest").mockResolvedValue(manifest([2025, 2025, 2024]));

    await useManifestStore.getState().load();

    expect(useManifestStore.getState().seasons).toEqual([2024, 2025]);
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
