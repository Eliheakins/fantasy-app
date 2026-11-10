import { describe, expect, it } from "vitest";

import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";

import { parseStartSit } from "./startSit";
import { parseTrade, planTrade, readTrade, tradeSummary } from "./tradeAsk";

const row = (gsis_id: string, display_name: string, position = "WR", team = "KC"): PlayerDictionaryRow => ({
  gsis_id,
  display_name,
  search_key: display_name.toLowerCase(),
  position,
  team,
});
const DICT = [
  row("kelce", "Travis Kelce", "TE"),
  row("kittle", "George Kittle", "TE", "SF"),
  row("hill", "Tyreek Hill"),
  row("chase", "Ja'Marr Chase", "WR", "CIN"),
  row("allen-qb", "Josh Allen", "QB", "BUF"),
  row("allen-lb", "Josh Allen", "LB", "JAX"),
];

describe("parseTrade", () => {
  it.each([
    ["trade Kelce for Kittle", ["Kelce"], ["Kittle"]],
    ["Should I trade Kelce for Kittle?", ["Kelce"], ["Kittle"]],
    ["Kelce for Kittle trade", ["Kelce"], ["Kittle"]],
    ["trade Kelce and Hill for Kittle", ["Kelce", "Hill"], ["Kittle"]],
    ["trade Kelce & Hill for Kittle and Chase.", ["Kelce", "Hill"], ["Kittle", "Chase"]],
  ])("reads %s", (q, give, get) => {
    expect(parseTrade(q)).toEqual({ give, get, hasVerb: !q.endsWith("trade") });
  });

  it.each([
    "Kelce or Kittle",
    "Mahomes vs Allen passing yards",
    "start Kelce or Kittle",
    "Kelce receptions",
    "trade Kelce",
    "trade for Kittle",
    "trade Kelce for",
    "trade A and B and C for D",
    "",
  ])("refuses %s", (q) => {
    expect(parseTrade(q)).toBeNull();
  });

  it("leaves start/sit phrasings to start/sit", () => {
    for (const q of ["start Kelce or Kittle", "Kelce or Kittle this week"]) {
      expect(parseStartSit(q)).not.toBeNull();
      expect(parseTrade(q)).toBeNull();
    }
  });
});

describe("readTrade", () => {
  it("resolves both sides to ids and names", () => {
    const read = readTrade("trade Kelce for Kittle", DICT);
    expect(read).toEqual({
      status: "resolved",
      outcome: { kind: "trade", give: ["kelce"], get: ["kittle"] },
      names: { kelce: "Travis Kelce", kittle: "George Kittle" },
      positions: { kelce: "TE", kittle: "TE" },
    });
  });

  it("is none for questions that are not trades", () => {
    expect(readTrade("Kelce or Kittle", DICT)).toEqual({ status: "none" });
  });

  it("is none for a bare 'A for B trade' with an unknown name, and a message with the trade verb", () => {
    expect(readTrade("Foo for Kittle trade", DICT)).toEqual({ status: "none" });
    expect(readTrade("trade Foo for Kittle", DICT).status).toBe("message");
  });

  it("asks which namesake when a name is ambiguous", () => {
    const read = readTrade("trade Josh Allen for Kittle", DICT);
    expect(read.status).toBe("choose");
  });

  it("refuses the same player on both sides", () => {
    expect(readTrade("trade Kelce for Kelce", DICT).status).toBe("message");
  });
});

const NAMES = { a: "Alpha", b: "Bravo", c: "Charlie", fa: "Free Guy", k: "Kicker Kim", d: "Denver D" };
const POSITIONS = { k: "K", d: "DEF" };
const OWNERS = [
  { gsis_id: "a", owner: "Me", roster_id: 1, is_mine: true },
  { gsis_id: "b", owner: "Rivals", roster_id: 7, is_mine: false },
  { gsis_id: "c", owner: "Others", roster_id: 8, is_mine: false },
  // two teams may share a name; the roster id still tells them apart
  { gsis_id: "e", owner: "Rivals", roster_id: 9, is_mine: false },
];
const plan = (give: string[], get: string[], owners = OWNERS) => planTrade({ give, get }, NAMES, owners, POSITIONS);

describe("planTrade", () => {
  it("takes the partner from the roster id of the get side's owner", () => {
    expect(plan(["a"], ["b"])).toEqual({
      kind: "evaluate",
      request: { partner_roster_id: 7, give_ids: ["a"], get_ids: ["b"] },
    });
    expect(plan(["a"], ["e"])).toMatchObject({ request: { partner_roster_id: 9 } });
  });

  it("hands off when the get side spans several teams, even teams sharing a name", () => {
    expect(plan(["a"], ["b", "c"])).toMatchObject({ kind: "handoff" });
    expect(plan(["a"], ["b", "e"])).toMatchObject({ kind: "handoff", text: expect.stringContaining("different teams") });
  });

  it("hands off for a free agent or unknown player on the get side", () => {
    expect(plan(["a"], ["fa"])).toMatchObject({ kind: "handoff", text: expect.stringContaining("Free Guy is a free agent") });
  });

  it("says kickers and defenses are not supported, not that they are free agents", () => {
    for (const [id, name] of [
      ["k", "Kicker Kim"],
      ["d", "Denver D"],
    ] as const) {
      const result = plan(["a"], [id]);
      expect(result).toMatchObject({ kind: "handoff", text: expect.stringContaining(name) });
      expect(result.kind === "handoff" && result.text).toMatch(/kickers and defenses are not supported/i);
      expect(result.kind === "handoff" && result.text).not.toMatch(/free agent/);
    }
  });

  it("hands off when the give side is not on the viewed roster", () => {
    expect(plan(["b"], ["c"])).toMatchObject({ kind: "handoff" });
  });

  it("hands off when the get player is already mine", () => {
    expect(plan(["a"], ["a"]).kind).toBe("handoff");
  });
});

describe("tradeSummary", () => {
  const me = (o: Partial<Record<string, number>>) => ({
    side: "me",
    roster_id: 1,
    team_name: "Me",
    playoff_before: 0.5,
    playoff_after: 0.5,
    title_before: 0.1,
    title_after: 0.1,
    wins_before: 8,
    wins_after: 8,
    ...o,
  });

  it("states the change in playoff and title odds in points, rounded like TradeResult", () => {
    expect(tradeSummary(me({ playoff_after: 0.485, title_after: 0.095 }))).toBe(
      "This trade lowers your playoff odds by 1.5 points and your title odds by 0.5 points.",
    );
  });

  it("says raises for gains and unchanged for a change that rounds to zero", () => {
    expect(tradeSummary(me({ playoff_after: 0.52, title_after: 0.1001 }))).toBe(
      "This trade raises your playoff odds by 2.0 points and leaves your title odds unchanged.",
    );
  });
});
