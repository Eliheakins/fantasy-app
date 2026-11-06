import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import { FIXTURE_SEASONS } from "@/stat/testing/seasons";

import { readOpponents } from "./opponents";
import { showIntent, showModelRanking } from "./paths/queryStates";
import type { AskActions } from "./paths/types";
import { readWho } from "./ranking";
import { resolvePlayers, tokenize } from "./resolvePlayers";
import { parseRules, splitAsked } from "./ruleParser";

const PLAYERS = JSON.parse(
  readFileSync(resolve(import.meta.dirname, "../../../../tests/stat/eval/players.fixture.json"), "utf8"),
) as PlayerDictionaryRow[];
const chipGroups = buildFilterChipGroups(FIXTURE_SEASONS);
const parse = (q: string) => parseRules(q, { matches: resolvePlayers(q, PLAYERS), seasons: FIXTURE_SEASONS, chipGroups });
const resolved = (q: string) => {
  const r = parse(q);
  if (r.status !== "resolved") throw new Error(`${q}: ${r.status} ${"reason" in r ? r.reason : ""}`);
  return r;
};

describe("side-by-side contrasts", () => {
  it("splits 2023 vs 2024 by season", () => {
    expect(splitAsked("Mahomes 2023 vs 2024 passing yards")).toBe("season");
    expect(resolved("Patrick Mahomes passing yards 2022 vs 2023").intent.filter_ids).toEqual(["season-2022", "season-2023"]);
  });

  it("splits home vs away by location, with neither chip as a filter", () => {
    expect(splitAsked("Justin Jefferson receiving yards at home vs away 2023")).toBe("location");
    expect(resolved("Travis Kelce receiving yards at home vs away in 2023").intent.filter_ids).toEqual(["season-2023"]);
  });

  it("keeps 'in 2022 and 2023' as two seasons added up", () => {
    expect(splitAsked("Mahomes passing yards in 2022 and 2023")).toBeNull();
  });
});

describe("opponents", () => {
  it("reads a team after 'against' or 'vs' as the defense the plays came against", () => {
    expect(readOpponents("Saquon Barkley rushing yards against the Cowboys", true).filters).toEqual(["opp-DAL"]);
    expect(resolved("Patrick Mahomes passing yards against the Chiefs in 2023").intent.filter_ids).toEqual(
      expect.arrayContaining(["opp-KC", "season-2023"]),
    );
  });

  it("keeps a lone team after 'against' as the subject when no player is named", () => {
    expect(readOpponents("passing yards against the Chiefs in 2023", false).filters).toEqual([]);
    expect(resolved("passing yards against the Chiefs in 2023").team).toEqual({ ids: ["KC"], side: "defense" });
  });

  it("reads a second team after 'against' as the opponent of the first", () => {
    const r = resolved("Chiefs passing yards against the Raiders in 2023");

    expect(r.team).toEqual({ ids: ["KC"], side: "offense" });
    expect(r.intent.filter_ids).toEqual(expect.arrayContaining(["opp-LV"]));
  });
});

describe("position and rookie filters on rankings", () => {
  it("reads position and rookie words", () => {
    expect(readWho(tokenize("which tight end has the most receiving yards"))).toMatchObject({ position: "TE", rookie: false });
    expect(readWho(tokenize("rookie leaders in receiving yards"))).toMatchObject({ position: null, rookie: true });
    expect(readWho(tokenize("top 5 rushers in yards per carry"))).toMatchObject({ position: null, role: "rusher" });
  });

  it("ranks one position, settling a generic stat to that position's own", () => {
    const r = resolved("top 10 running backs by epa per play 2025");

    expect(r.leaderboard).toMatchObject({ position: "RB", limit: 10 });
    const answer = vi.fn();
    showModelRanking(r.intent, "top 10 running backs by epa per play 2025", "rules", [], { answer, fail: vi.fn() } as unknown as AskActions, {
      seasons: [2025],
    });
    expect(answer.mock.calls[0]![0]).toMatchObject({ position: "RB", stats: ["rush_epa"], order: { metric: "rush_epa" } });
  });

  it("reads 'rushers by EPA' as the rushers' own EPA", () => {
    const r = resolved("top 10 rushers by epa per play 2025");

    expect(r.intent.stat_ids).toEqual(["rush_epa"]);
    expect(r.leaderboard?.order.metric).toBe("rush_epa");
  });

  it("refuses a role noun the stat does not count", () => {
    expect(parse("top 10 receivers in yards per carry 2025").status).toBe("ambiguous");
  });
});

describe("stat lines", () => {
  it("answers 'X stats' with the position's usual stats", () => {
    const answer = vi.fn();
    const r = resolved("tyreek hill 2023 stats");
    const hill = resolvePlayers("tyreek hill", PLAYERS)[0]!.candidates[0]!;
    showIntent([hill], r.intent, "tyreek hill 2023 stats", "rules", [], { answer, fail: vi.fn() } as unknown as AskActions, {
      seasons: [2023],
    });

    expect(answer.mock.calls[0]![0].stats).toEqual(["rec_tgt", "rec_receptions", "rec_yards", "rec_tds"]);
  });
});
