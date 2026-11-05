import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchManifest } from "./api";
import { manifestSchema } from "./schemas/manifest";

const VALID = {
  schema_version: 1,
  built_at: "2026-11-04T12:00:00+00:00",
  nflreadpy_version: "0.1.0",
  seasons: [
    { season: 2025, path: "nfl_pbp_2025.parquet", rows: 34632, max_week: 22, has_participation: true },
    { season: 2026, path: "nfl_pbp_2026.parquet", rows: 9000, max_week: null, has_participation: false },
  ],
  player_index: { path: "player_index.parquet", rows: 5854 },
};

function respond(body: unknown, init: ResponseInit = { status: 200 }) {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify(body), init));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("manifestSchema", () => {
  it("accepts the manifest the build writes", () => {
    expect(manifestSchema.safeParse(VALID).success).toBe(true);
  });

  it("accepts a manifest with no player index", () => {
    expect(manifestSchema.safeParse({ ...VALID, player_index: null }).success).toBe(true);
  });

  it("reads the player-game table entry, and treats a missing key as no table", () => {
    const withTable = { ...VALID, player_game: { path: "player_game.parquet", rows: 94848 } };

    expect(manifestSchema.parse(withTable).player_game?.rows).toBe(94848);
    expect(manifestSchema.parse(VALID).player_game).toBeNull();
  });

  it("reads the players file entry, and treats a missing key as no players file", () => {
    const withPlayers = { ...VALID, players: { path: "players.json", rows: 3062 } };

    expect(manifestSchema.parse(withPlayers).players?.rows).toBe(3062);
    expect(manifestSchema.parse(VALID).players).toBeNull();
  });

  it("rejects a players path that could leave the data folder or is not JSON", () => {
    for (const path of ["../players.json", "/players.json", "a/b.json", "players.parquet"]) {
      expect(manifestSchema.safeParse({ ...VALID, players: { path, rows: 1 } }).success).toBe(false);
    }
  });

  it("rejects a manifest without seasons", () => {
    expect(manifestSchema.safeParse({ ...VALID, seasons: "nope" }).success).toBe(false);
  });

  it("rejects a manifest version it does not know", () => {
    expect(manifestSchema.safeParse({ ...VALID, schema_version: 2 }).success).toBe(false);
  });

  it("rejects file paths that could leave the data folder", () => {
    for (const path of ["../x.parquet", "/etc/x.parquet", "//evil.example/x.parquet", "a/b.parquet"]) {
      const tampered = { ...VALID, seasons: [{ ...VALID.seasons[0], path }] };

      expect(manifestSchema.safeParse(tampered).success).toBe(false);
    }
  });
});

describe("fetchManifest", () => {
  it("returns the parsed manifest from the data folder", async () => {
    const fetchMock = respond(VALID);
    vi.stubGlobal("fetch", fetchMock);

    const manifest = await fetchManifest();

    expect(manifest.seasons.map((s) => s.season)).toEqual([2025, 2026]);
    expect(String(fetchMock.mock.calls[0]![0])).toMatch(/\/data\/manifest\.json$/);
  });

  it("tells the user to build the data when the manifest is missing", async () => {
    vi.stubGlobal("fetch", respond({ detail: "Not Found" }, { status: 404 }));

    await expect(fetchManifest()).rejects.toThrow(/make stat-data/);
  });

  it("says the API is not reachable when the request itself fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(fetchManifest()).rejects.toThrow(/not reachable/);
  });

  it("names the first problem in plain words when the manifest has the wrong shape", async () => {
    vi.stubGlobal("fetch", respond({ ...VALID, seasons: "nope" }));

    const error = await fetchManifest().catch((e: Error) => e);

    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toMatch(/unexpected shape.*seasons/i);
    expect((error as Error).message).not.toContain("\n");
  });

  it("explains a response that is not JSON instead of leaking a parse error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<!doctype html><html></html>", { status: 200 })));

    await expect(fetchManifest()).rejects.toThrow(/not JSON/);
  });

  it("never reuses a cached manifest, so a rebuild shows up on the next load", async () => {
    const fetchMock = respond(VALID);
    vi.stubGlobal("fetch", fetchMock);

    await fetchManifest();

    expect(fetchMock.mock.calls[0]![1]).toMatchObject({ cache: "no-store" });
  });
});
