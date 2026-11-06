import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";

import { readFantasyRoute } from "./fantasyRoute";

const PLAYERS = JSON.parse(
  readFileSync(resolve(import.meta.dirname, "../../../../tests/stat/eval/players.fixture.json"), "utf8"),
) as PlayerDictionaryRow[];
const route = (q: string) => readFantasyRoute(q, PLAYERS);

describe("readFantasyRoute", () => {
  it("sends waiver and drop questions to Moves", () => {
    expect(route("who should I pick up on waivers")?.to).toBe("/moves?view=fa");
    expect(route("who should I drop")?.to).toBe("/moves?view=fa");
  });

  it("sends a player's injury or projection to his page", () => {
    const injury = route("is Travis Kelce injured");
    const projection = route("Patrick Mahomes rest of season projection");

    expect(injury?.to).toMatch(/^\/players\//);
    expect(injury?.text).toMatch(/injury status/);
    expect(projection?.to).toMatch(/^\/players\//);
  });

  it("sends byes and this week's games to the Lineup page", () => {
    expect(route("when is the Chiefs bye week")?.to).toBe("/lineup");
    expect(route("who does Travis Kelce play this week")?.to).toBe("/lineup");
  });

  it("says when no page has the answer", () => {
    expect(route("easiest remaining schedule for running backs")).toMatchObject({ to: null });
  });

  it("leaves stat questions to the stat paths", () => {
    expect(route("Travis Kelce receptions in 2023")).toBeNull();
    expect(route("Davante Adams drop rate")).toBeNull();
    expect(route("Kelce receiving yards at home")).toBeNull();
  });
});
