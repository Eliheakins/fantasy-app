import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Manifest } from "./schemas/manifest";

import { getPlayerDictionary, getPlayers, getPlayersByIds, playerDictionary, searchPlayers } from "./players";

const MAHOMES = {
  gsis_id: "00-0033873",
  full_name: "Patrick Mahomes",
  position: "QB",
  team: "KC",
  headshot_url: null,
  birth_date: "1995-09-17",
  years_exp: 8,
};
const KELCE = {
  gsis_id: "00-0030506",
  full_name: "Travis Kelce",
  position: "TE",
  team: "KC",
  headshot_url: null,
  birth_date: null,
  years_exp: 11,
};
const FILE = { schema_version: 1, players: [MAHOMES, KELCE] };

let buildCount = 0;
// A new build stamp per test, so the keyed cache never carries a load from one test to the next.
const freshManifest = (): Manifest => ({
  schema_version: 1,
  built_at: "2026-11-04T12:00:00+00:00",
  nflreadpy_version: "0.1.0",
  seasons: [],
  player_index: null,
  player_game: null,
  players: { path: "players.json", rows: 2 },
});

let MANIFEST = freshManifest();

beforeEach(() => {
  buildCount += 1;
  MANIFEST = { ...freshManifest(), built_at: `2026-11-04T12:00:${String(buildCount).padStart(2, "0")}+00:00` };
});

describe("searchPlayers", () => {
  const players = [MAHOMES, KELCE];

  it("matches a name fragment case-insensitively", () => {
    expect(searchPlayers(players, "KELC").map((p) => p.gsis_id)).toEqual(["00-0030506"]);
  });

  it("returns nothing for a blank query and caps the results", () => {
    expect(searchPlayers(players, "   ")).toEqual([]);
    expect(searchPlayers(players, "a", 1)).toHaveLength(1);
  });
});

describe("playerDictionary", () => {
  it("gives each player a display name and a lowercase search key", () => {
    expect(playerDictionary([MAHOMES])).toEqual([
      {
        gsis_id: "00-0033873",
        display_name: "Patrick Mahomes",
        search_key: "patrick mahomes",
        position: "QB",
        team: "KC",
      },
    ]);
  });
});

describe("getPlayers", () => {
  it("reads the file the manifest names from the data location, once", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(FILE)));
    vi.stubGlobal("fetch", fetchMock);

    const first = await getPlayers(MANIFEST);
    const second = await getPlayers(MANIFEST);

    expect(first.map((p) => p.full_name)).toEqual(["Patrick Mahomes", "Travis Kelce"]);
    expect(second).toBe(first);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]![0])).toMatch(/\/data\/players\.json$/);
  });

  it("revalidates the file on load, so a rebuild's new list is not hidden by the browser cache", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(FILE)));
    vi.stubGlobal("fetch", fetchMock);

    await getPlayers(MANIFEST);

    expect(fetchMock.mock.calls[0]![1]).toMatchObject({ cache: "no-cache" });
  });

  it("drops a headshot address that is not https instead of rejecting the whole list", async () => {
    const odd = { ...MAHOMES, headshot_url: "javascript:alert(1)" };
    const ok = { ...KELCE, headshot_url: "https://x/k.png" };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => new Response(JSON.stringify({ schema_version: 1, players: [odd, ok] }))),
    );

    const players = await getPlayers(MANIFEST);

    expect(players.map((p) => p.headshot_url)).toEqual([null, "https://x/k.png"]);
  });

  it("tells the user to rebuild when the manifest lists no players file", async () => {
    const noPlayers = { ...MANIFEST, players: null };

    await expect(getPlayers(noPlayers)).rejects.toThrow(/make stat-data/);
  });

  it("does not cache a failed load, so the next ask retries", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch")));
    await expect(getPlayers(MANIFEST)).rejects.toThrow(/not reachable/);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => new Response(JSON.stringify(FILE))),
    );

    expect(await getPlayers(MANIFEST)).toHaveLength(2);
  });

  it("rejects a players file with the wrong shape", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => new Response(JSON.stringify({ schema_version: 1, players: [{ gsis_id: "" }] }))),
    );

    await expect(getPlayers(MANIFEST)).rejects.toThrow(/unexpected shape/);
  });
});

describe("players cache", () => {
  const fetchMock = () => {
    const f = vi.fn().mockImplementation(async () => new Response(JSON.stringify(FILE)));
    vi.stubGlobal("fetch", f);
    return f;
  };

  it("reuses the load for the same manifest build", async () => {
    const f = fetchMock();
    const build = { ...MANIFEST, built_at: "2030-01-01T00:00:00+00:00" };

    await getPlayers(build);
    await getPlayers({ ...build });

    expect(f).toHaveBeenCalledTimes(1);
  });

  it("loads again when the manifest is a new build or names another file", async () => {
    const f = fetchMock();
    const build = { ...MANIFEST, built_at: "2031-01-01T00:00:00+00:00" };

    await getPlayers(build);
    await getPlayers({ ...build, built_at: "2031-02-01T00:00:00+00:00" });
    await getPlayers({ ...build, built_at: "2031-02-01T00:00:00+00:00", players: { path: "p2.json", rows: 2 } });

    expect(f).toHaveBeenCalledTimes(3);
  });
});

describe("derived lookups", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => new Response(JSON.stringify(FILE))),
    );
  });

  it("builds the dictionary from the same file, once", async () => {
    const dictionary = await getPlayerDictionary(MANIFEST);

    expect(dictionary.map((d) => d.search_key)).toEqual(["patrick mahomes", "travis kelce"]);
    expect(await getPlayerDictionary(MANIFEST)).toBe(dictionary);
  });

  it("looks players up by id in the order asked, skipping unknown ids", async () => {
    const found = await getPlayersByIds(MANIFEST, ["00-0030506", "nope", "00-0033873"]);

    expect(found.map((p) => p.full_name)).toEqual(["Travis Kelce", "Patrick Mahomes"]);
  });
});
