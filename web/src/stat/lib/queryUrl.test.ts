import { describe, expect, it } from "vitest";

import { buildFilterChipGroups, getAllFilterChipIds } from "@/stat/config/queryBuilderOptions";

import {
  applyFilterGroup,
  clearPins,
  EMPTY_QUERY,
  ignoredFilterIds,
  isLeagueQuery,
  MAX_PINNED_PLAYERS,
  MAX_SELECTED_STATS,
  parseQuery,
  pinPlayer,
  queryKey,
  type QueryState,
  serializeQuery,
  setGranularity,
  setMinPlays,
  setRanking,
  setRoster,
  setSide,
  setSplit,
  setSubject,
  toggleFilter,
  toggleStat,
  toggleTeam,
  unpinPlayer,
  writeQuery,
} from "./queryUrl";

const KNOWN_FILTERS = new Set(getAllFilterChipIds(buildFilterChipGroups([2023, 2024])));
const params = (search: string) => new URLSearchParams(search);
const parse = (search: string) => parseQuery(params(search), KNOWN_FILTERS);

const FULL: QueryState = {
  players: ["00-0033873", "00-0034857"],
  stats: ["pass_yards", "pass_tds"],
  filters: ["season-2023", "stype-reg", "down-3"],
  granularity: "per_game",
  minPlays: 25,
  order: null,
  limit: null,
  split: null,
  subject: "players",
  teams: [],
  side: "offense",
  roster: "mine",
  lastGames: 3,
  position: "WR",
  rookie: true,
};

describe("serializeQuery and parseQuery", () => {
  it("round-trips a full query", () => {
    expect(parse(serializeQuery(FULL).toString())).toEqual(FULL);
  });

  it("writes readable repeated parameters, one per player, stat and filter", () => {
    const text = serializeQuery({
      ...EMPTY_QUERY,
      players: ["00-0033873"],
      stats: ["pass_yards"],
      filters: ["season-2023"],
    }).toString();

    expect(text).toBe("p=00-0033873&s=pass_yards&f=season-2023");
  });

  it("leaves out anything at its default, so the empty query is an empty string", () => {
    expect(serializeQuery(EMPTY_QUERY).toString()).toBe("");
    expect(serializeQuery({ ...EMPTY_QUERY, granularity: "per_game" }).toString()).toBe("g=per_game");
    expect(serializeQuery({ ...EMPTY_QUERY, minPlays: 10 }).toString()).toBe("m=10");
  });

  it("writes the league filter as lg and reads it back", () => {
    for (const roster of ["mine", "rostered", "fa"] as const) {
      const text = serializeQuery({ ...EMPTY_QUERY, roster }).toString();
      expect(text).toBe(`lg=${roster}`);
      expect(parse(text).roster).toBe(roster);
    }
    expect(queryKey({ ...EMPTY_QUERY, roster: "fa" })).not.toBe(queryKey(EMPTY_QUERY));
  });

  it("ignores a bad lg value, and absent means all players", () => {
    expect(parse("lg=everyone").roster).toBeNull();
    expect(parse("lg=").roster).toBeNull();
    expect(parse("").roster).toBeNull();
  });

  it("sets and clears the league filter without touching the rest", () => {
    const withPin = pinPlayer(EMPTY_QUERY, "00-1");
    expect(setRoster(withPin, "fa")).toEqual({ ...withPin, roster: "fa" });
    expect(setRoster(setRoster(withPin, "fa"), null)).toEqual(withPin);
  });

  it("parses an empty or unrelated query string to the empty query", () => {
    expect(parse("")).toEqual(EMPTY_QUERY);
    expect(parse("utm_source=x&q=hello")).toEqual(EMPTY_QUERY);
  });

  it("drops stat ids the app does not know, repeats, and anything past the cap", () => {
    const many = ["pass_yards", "pass_tds", "rec_yards", "rec_receptions", "rush_yards", "rush_tds"];

    expect(parse("s=nope&s=pass_yards&s=pass_yards").stats).toEqual(["pass_yards"]);
    expect(parse(many.map((s) => `s=${s}`).join("&")).stats).toHaveLength(MAX_SELECTED_STATS);
  });

  it("drops player ids that are not plain ids, repeats, and anything past the pin limit", () => {
    const ids = Array.from({ length: 8 }, (_, i) => `00-000000${i}`);

    expect(parse("p=%3Cscript%3E&p=a b&p=00-0033873&p=00-0033873").players).toEqual(["00-0033873"]);
    expect(parse(ids.map((p) => `p=${p}`).join("&")).players).toHaveLength(MAX_PINNED_PLAYERS);
  });

  it("drops filter ids that are not chips in the current data", () => {
    expect(parse("f=season-2023&f=season-1999&f=bogus").filters).toEqual(["season-2023"]);
  });

  it("falls back to the default granularity for a value it does not know", () => {
    expect(parse("g=weekly").granularity).toBe("per_play");
    expect(parse("g=total&s=pass_yards").granularity).toBe("total");
  });

  it("forces per-play when a rate stat is selected, as the query builder always did", () => {
    expect(parse("s=eff_epa&g=total").granularity).toBe("per_play");
    expect(parse("s=eff_epa&s=pass_yards&g=per_game").granularity).toBe("per_play");
  });

  it("clamps the minimum plays to a whole number from 0 to 500 and ignores junk", () => {
    expect(parse("m=25.7").minPlays).toBe(26);
    expect(parse("m=-4").minPlays).toBe(0);
    expect(parse("m=9000").minPlays).toBe(500);
    expect(parse("m=lots").minPlays).toBe(0);
  });

  it("accepts any well-formed filter id when the chips are not known yet", () => {
    expect(parseQuery(params("f=season-2023&f=%3Cx%3E")).filters).toEqual(["season-2023"]);
  });
});

describe("ignoredFilterIds", () => {
  it("lists the filters in a link that the current data has no chip for", () => {
    const search = params("f=season-2023&f=season-1999&f=bogus&f=%3Cx%3E");

    expect(ignoredFilterIds(search, parseQuery(search, KNOWN_FILTERS))).toEqual(["season-1999", "bogus", "<x>"]);
  });

  it("is empty when every filter in the link is applied", () => {
    const search = params("f=season-2023&f=down-3");

    expect(ignoredFilterIds(search, parseQuery(search, KNOWN_FILTERS))).toEqual([]);
  });

  it("lists a repeated unknown filter once", () => {
    const search = params("f=old&f=old");

    expect(ignoredFilterIds(search, parseQuery(search, KNOWN_FILTERS))).toEqual(["old"]);
  });
});

describe("queryKey", () => {
  it("is the same for equal queries and differs when any part differs", () => {
    expect(queryKey({ ...FULL })).toBe(queryKey({ ...FULL, players: [...FULL.players] }));
    for (const changed of [
      { players: ["00-0033873"] },
      { stats: ["pass_yards"] },
      { filters: ["season-2024"] },
      { granularity: "total" as const },
      { minPlays: 26 },
    ]) {
      expect(queryKey({ ...FULL, ...changed })).not.toBe(queryKey(FULL));
    }
  });
});

describe("writeQuery", () => {
  it("replaces the query keys and keeps every other parameter, such as the question", () => {
    const next = writeQuery(params("q=Mahomes+yards&p=old&s=pass_tds&g=total"), {
      ...EMPTY_QUERY,
      players: ["00-0033873"],
      stats: ["pass_yards"],
    });

    expect(next.get("q")).toBe("Mahomes yards");
    expect(next.getAll("p")).toEqual(["00-0033873"]);
    expect(next.getAll("s")).toEqual(["pass_yards"]);
    expect(next.has("g")).toBe(false);
  });

  it("does not modify the parameters it was given", () => {
    const original = params("p=a&s=pass_yards");

    writeQuery(original, EMPTY_QUERY);

    expect(original.toString()).toBe("p=a&s=pass_yards");
  });
});

describe("query transitions", () => {
  it("adds and removes a stat, and stops at the cap", () => {
    let state = toggleStat(EMPTY_QUERY, "pass_yards");
    expect(state.stats).toEqual(["pass_yards"]);

    state = toggleStat(state, "pass_yards");
    expect(state.stats).toEqual([]);

    for (const id of ["pass_yards", "pass_tds", "rec_yards", "rec_receptions", "rush_yards", "rush_tds"]) {
      state = toggleStat(state, id);
    }
    expect(state.stats).toHaveLength(MAX_SELECTED_STATS);
  });

  it("ignores a stat id it does not know", () => {
    expect(toggleStat(EMPTY_QUERY, "nope")).toEqual(EMPTY_QUERY);
  });

  it("moves to per-play when a rate stat is added, and keeps the choice otherwise", () => {
    const total = setGranularity(toggleStat(EMPTY_QUERY, "pass_yards"), "total");

    expect(toggleStat(total, "eff_epa").granularity).toBe("per_play");
    expect(setGranularity(toggleStat(EMPTY_QUERY, "eff_epa"), "per_game").granularity).toBe("per_play");
    expect(total.granularity).toBe("total");
  });

  it("sets the minimum plays within bounds", () => {
    expect(setMinPlays(EMPTY_QUERY, 40.4).minPlays).toBe(40);
    expect(setMinPlays(EMPTY_QUERY, 900).minPlays).toBe(500);
    expect(setMinPlays(EMPTY_QUERY, -1).minPlays).toBe(0);
  });

  it("toggles one filter chip", () => {
    const on = toggleFilter(EMPTY_QUERY, "down-3");
    expect(on.filters).toEqual(["down-3"]);
    expect(toggleFilter(on, "down-3").filters).toEqual([]);
  });

  it("sets exactly the chosen chips of a group and leaves other groups alone", () => {
    const start: QueryState = { ...EMPTY_QUERY, filters: ["down-1", "down-3", "qtr-4"] };

    const next = applyFilterGroup(start, ["down-1", "down-2", "down-3", "down-4"], ["down-2"]);

    expect(next.filters).toEqual(["qtr-4", "down-2"]);
  });

  it("pins a player once, up to the limit, and refuses beyond that", () => {
    let state = pinPlayer(EMPTY_QUERY, "a");
    expect(pinPlayer(state, "a")).toEqual(state);

    for (let i = 0; i < MAX_PINNED_PLAYERS + 2; i++) {
      state = pinPlayer(state, `p${i}`);
    }
    expect(state.players).toHaveLength(MAX_PINNED_PLAYERS);
  });

  it("unpins one player and clears all, without touching the rest of the query", () => {
    const state = unpinPlayer(FULL, "00-0033873");
    expect(state.players).toEqual(["00-0034857"]);
    expect(state.stats).toEqual(FULL.stats);

    expect(clearPins(FULL).players).toEqual([]);
    expect(clearPins(FULL).filters).toEqual(FULL.filters);
  });

  it("never mutates the state it is given", () => {
    const frozen = Object.freeze({ ...FULL, players: Object.freeze([...FULL.players]) as string[] });

    expect(() => pinPlayer(frozen, "x")).not.toThrow();
    expect(frozen.players).toEqual(FULL.players);
  });
});

describe("leaderboard parts of the URL", () => {
  const board: QueryState = {
    ...EMPTY_QUERY,
    stats: ["pass_yards"],
    filters: ["season-2023"],
    order: { metric: "pass_yards", direction: "desc" },
    limit: 10,
  };

  it("writes the order as o and the limit as n", () => {
    expect(serializeQuery(board).toString()).toBe("s=pass_yards&f=season-2023&o=pass_yards&n=10");
    expect(serializeQuery({ ...board, order: { metric: "pass_yards", direction: "asc" } }).toString()).toContain("o=pass_yards%3Aasc");
  });

  it("round-trips an order and a limit", () => {
    expect(parse(serializeQuery(board).toString())).toEqual(board);
    const ascending = { ...board, order: { metric: "pass_yards", direction: "asc" as const } };
    expect(parse(serializeQuery(ascending).toString())).toEqual(ascending);
  });

  it("drops an order that names a stat the query does not select", () => {
    expect(parse("s=pass_yards&o=rush_yards&n=5").order).toBeNull();
    expect(parse("o=pass_yards&n=5").order).toBeNull();
  });

  it("drops a limit with no order, which would cut unsorted rows", () => {
    expect(parse("s=pass_yards&n=5").limit).toBeNull();
  });

  it("drops a limit that is not a whole number from 1 to 100", () => {
    for (const bad of ["0", "101", "-3", "abc", "2.5", ""]) {
      expect(parse(`s=pass_yards&o=pass_yards&n=${bad}`).limit, bad).toBeNull();
    }
    expect(parse("s=pass_yards&o=pass_yards&n=100").limit).toBe(100);
  });

  it("is a league query only with no players, an order and a limit", () => {
    expect(isLeagueQuery(board)).toBe(true);
    expect(isLeagueQuery({ ...board, players: ["00-0033873"] })).toBe(false);
    expect(isLeagueQuery({ ...board, limit: null })).toBe(false);
    expect(isLeagueQuery({ ...board, order: null })).toBe(false);
  });

  it("clears the order and its limit when the ordering stat is deselected", () => {
    expect(toggleStat(board, "pass_yards").order).toBeNull();
    expect(toggleStat(board, "pass_yards").limit).toBeNull();
    expect(toggleStat(board, "pass_tds").order).toEqual(board.order);
  });

  it("sets a ranking by a selected stat, starting at the top 10", () => {
    const query = { ...EMPTY_QUERY, stats: ["pass_yards", "pass_tds"] };

    const ranked = setRanking(query, { metric: "pass_tds", direction: "asc" });

    expect(ranked.order).toEqual({ metric: "pass_tds", direction: "asc" });
    expect(ranked.limit).toBe(10);
    expect(ranked.stats).toEqual(query.stats);
  });

  it("keeps the limit already set when only the order changes", () => {
    expect(setRanking(board, { metric: "pass_yards", direction: "asc" }).limit).toBe(10);
    expect(setRanking({ ...board, limit: 25 }, { metric: "pass_yards", direction: "asc" }).limit).toBe(25);
  });

  it("keeps the limit between 1 and 100, and a non-number gives the default", () => {
    expect(setRanking(board, board.order, 500).limit).toBe(100);
    expect(setRanking(board, board.order, 0).limit).toBe(1);
    expect(setRanking(board, board.order, Number.NaN).limit).toBe(10);
  });

  it("will not rank by a stat the query does not select", () => {
    expect(setRanking(board, { metric: "rush_yards", direction: "desc" })).toBe(board);
  });

  it("clears the order and the limit together", () => {
    const cleared = setRanking(board, null);

    expect(cleared.order).toBeNull();
    expect(cleared.limit).toBeNull();
  });

  it("tells a leaderboard from the same query without one", () => {
    expect(queryKey(board)).not.toBe(queryKey({ ...board, limit: null, order: null }));
    expect(queryKey(board)).not.toBe(queryKey({ ...board, limit: 5 }));
  });
});

describe("splitting by season or week in the URL", () => {
  const split = { ...FULL, split: "season" as const };

  it("writes the split as by and reads it back", () => {
    expect(serializeQuery(split).get("by")).toBe("season");
    expect(parse(serializeQuery(split).toString())).toEqual(split);
    expect(parse(serializeQuery({ ...FULL, split: "week" }).toString()).split).toBe("week");
  });

  it("reads anything else as no split", () => {
    expect(parse("s=pass_yards&by=quarter").split).toBeNull();
    expect(parse("s=pass_yards").split).toBeNull();
  });

  it("tells a split query from the same query without one", () => {
    expect(queryKey(split)).not.toBe(queryKey(FULL));
  });

  it("sets and clears the split", () => {
    expect(setSplit(FULL, "week").split).toBe("week");
    expect(setSplit(split, null).split).toBeNull();
  });
});

describe("team subjects in the URL", () => {
  const teams: QueryState = { ...FULL, players: [], subject: "teams", teams: ["KC", "BUF"], side: "defense" };

  it("writes who=teams, the teams and the side, and reads them back", () => {
    const written = serializeQuery(teams);

    expect(written.get("who")).toBe("teams");
    expect(written.getAll("t")).toEqual(["KC", "BUF"]);
    expect(written.get("side")).toBe("defense");
    expect(parse(written.toString())).toEqual(teams);
  });

  it("leaves the default subject and side out of the URL", () => {
    const written = serializeQuery(FULL);

    expect(written.has("who")).toBe(false);
    expect(written.has("side")).toBe(false);
  });

  it("drops team ids the data does not have", () => {
    expect(parse("who=teams&t=KC&t=XYZ&s=pass_yards").teams).toEqual(["KC"]);
  });

  it("is a league query for teams when no team is named", () => {
    const ranked = { ...teams, teams: [], order: { metric: "pass_yards", direction: "desc" as const }, limit: 5 };

    expect(isLeagueQuery(ranked)).toBe(true);
    expect(isLeagueQuery({ ...ranked, teams: ["KC"] })).toBe(false);
  });

  it("toggles a team, up to the cap", () => {
    expect(toggleTeam(teams, "KC").teams).toEqual(["BUF"]);
    expect(toggleTeam(teams, "DAL").teams).toEqual(["KC", "BUF", "DAL"]);
    expect(toggleTeam(teams, "XYZ")).toBe(teams);
    const full = { ...teams, teams: ["KC", "BUF", "DAL", "PHI", "SF"] };
    expect(toggleTeam(full, "DET")).toBe(full);
  });

  it("switches the subject and the side", () => {
    expect(setSubject(FULL, "teams").subject).toBe("teams");
    const ranked = { ...FULL, order: { metric: "pass_yards", direction: "desc" as const }, limit: 5 };
    expect(setSubject(ranked, "teams")).toMatchObject({ order: null, limit: null });
    expect(setSide(teams, "offense").side).toBe("offense");
  });

  it("tells a team query from a player query with the same stats", () => {
    expect(queryKey(teams)).not.toBe(queryKey({ ...teams, side: "offense" }));
  });
});
