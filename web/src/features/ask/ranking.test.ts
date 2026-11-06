import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import { FIXTURE_SEASONS } from "@/stat/testing/seasons";

import { NO_PLAYER_MESSAGE, showModelRanking } from "./paths/queryStates";
import type { AskActions } from "./paths/types";
import { leaderboardFor, readMinimum } from "./ranking";
import { resolvePlayers, tokenize } from "./resolvePlayers";
import { parseRules } from "./ruleParser";

const PLAYERS = JSON.parse(
  readFileSync(resolve(import.meta.dirname, "../../../../tests/stat/eval/players.fixture.json"), "utf8"),
) as PlayerDictionaryRow[];
const chipGroups = buildFilterChipGroups(FIXTURE_SEASONS);
const parse = (q: string) => parseRules(q, { matches: resolvePlayers(q, PLAYERS), seasons: FIXTURE_SEASONS, chipGroups });
const board = (q: string) => {
  const r = parse(q);
  if (r.status !== "resolved" || !r.leaderboard) throw new Error(`${q}: ${r.status} ${"reason" in r ? r.reason : ""}`);
  return { intent: r.intent, board: r.leaderboard };
};

describe("leaderboardFor", () => {
  const tokens = (q: string) => tokenize(q);

  it("puts a floor under fewest-first counts and rates, not under most-first totals", () => {
    const most = leaderboardFor(tokens("most interceptions"), "pass_int", "total", { teams: false, defense: false, weekly: false });
    const fewest = leaderboardFor(tokens("fewest interceptions"), "pass_int", "total", { teams: false, defense: false, weekly: false });
    const rate = leaderboardFor(tokens("best ypc"), "ypc", "per_play", { teams: false, defense: false, weekly: false });

    expect(most).toMatchObject({ order: { direction: "desc" }, minPlays: 0 });
    expect(fewest).toMatchObject({ order: { direction: "asc" }, minPlays: 100 });
    expect(rate).toMatchObject({ minPlays: 100, limit: 10 });
  });

  it("takes a floor in words only when it counts the ranked stat's plays", () => {
    expect(readMinimum(tokens("best ypc min 100 carries"))).toMatchObject({ min: 100, role: "rusher" });
    expect(readMinimum(tokens("catch rate at least 50 targets"))).toMatchObject({ min: 50, role: "receiver" });
    expect(leaderboardFor(tokens("best ypc min 50 targets"), "ypc", "per_play", { teams: false, defense: false, weekly: false })).toHaveProperty("reason");
  });

  it("ranks a defense's allowed stat best when it allows least", () => {
    const best = leaderboardFor(tokens("best defense"), "team_epa", "per_play", { teams: true, defense: true, weekly: false });

    expect(best).toMatchObject({ order: { direction: "asc" }, minPlays: 0 });
  });
});

describe("rules vocabulary for rankings", () => {
  it("reads 'leads' as a ranking", () => {
    expect(board("who leads the league in passing touchdowns").board.order).toEqual({ metric: "pass_tds", direction: "desc" });
  });

  it("reads a floor in words", () => {
    const { intent, board: b } = board("best yards per carry min 100 carries 2025");

    expect(intent.stat_ids).toEqual(["ypc"]);
    expect(b.minPlays).toBe(100);
  });

  it("reads 'in a single game' as a ranking of single games", () => {
    expect(board("most passing yards in a single game 2025").board.minPlays).toBe(0);
  });

  it("reads 'by' and 'among qualified' as filler in a ranking", () => {
    expect(board("lowest interception rate 2025 among qualified").board.order.direction).toBe("asc");
  });

  it("reads 'who had more A or B' as a comparison of two players", () => {
    const r = parse("who had more rushing yards in 2024, Henry or Barkley");

    expect(r.status).toBe("resolved");
    expect(r.status === "resolved" && r.intent.stat_ids).toEqual(["rush_yards"]);
  });
});

describe("rankings the model read", () => {
  const SCOPE = { seasons: [2025, 2026], maxWeeks: { 2026: 8 } };
  const actions = () => ({ fail: vi.fn(), answer: vi.fn() }) as unknown as AskActions & { fail: ReturnType<typeof vi.fn>; answer: ReturnType<typeof vi.fn> };
  const intent = { stat_ids: ["rush_yards"], filter_ids: [], granularity: "total" as const };

  it("ranks by the first stat when the words ask for a ranking", () => {
    const a = actions();
    showModelRanking(intent, "leading rusher in week 5", "model", [], a, SCOPE);

    const state = a.answer.mock.calls[0]![0];
    expect(state).toMatchObject({ players: [], order: { metric: "rush_yards", direction: "desc" }, limit: 10 });
    expect(state.filters).toEqual(expect.arrayContaining(["wk-5", "season-2026"]));
  });

  it("ranks when the model read a ranking the words do not show", () => {
    const a = actions();
    showModelRanking({ ...intent, ranking: true }, "whose rushing yards are highest", "model", [], a, SCOPE);

    expect(a.answer).toHaveBeenCalled();
  });

  it("refuses a question that names no one and asks for no ranking", () => {
    const a = actions();
    showModelRanking(intent, "Jefferon receiving yards 2024", "model", [], a, SCOPE);

    expect(a.fail).toHaveBeenCalledWith("Jefferon receiving yards 2024", "model", NO_PLAYER_MESSAGE);
  });

  it("ranks teams, on defense when the words say so", () => {
    const a = actions();
    showModelRanking(intent, "which team allowed the most rushing yards this season", "model", [], a, SCOPE);

    expect(a.answer.mock.calls[0]![0]).toMatchObject({ subject: "teams", teams: [], side: "defense", filters: ["season-2026", "stype-reg"] });
  });
});
