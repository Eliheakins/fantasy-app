import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { buildFilterChipGroups, CHIP_COMBO_PHRASES, CHIP_PHRASES } from "@/stat/config/queryBuilderOptions";
import { STAT_DEFINITIONS } from "@/stat/config/statDictionary";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import { FIXTURE_SEASONS } from "@/stat/testing/seasons";

import { resolvePlayers, tokenize } from "./resolvePlayers";
import { parseRules, splitAsked } from "./ruleParser";

const PLAYERS = JSON.parse(
  readFileSync(resolve(import.meta.dirname, "../../../../tests/stat/eval/players.fixture.json"), "utf8"),
) as PlayerDictionaryRow[];

const chipGroups = buildFilterChipGroups(FIXTURE_SEASONS);
const chipIds = new Set(chipGroups.flatMap((g) => g.options.map((o) => o.id)));

function parse(question: string) {
  return parseRules(question, { matches: resolvePlayers(question, PLAYERS), seasons: FIXTURE_SEASONS, chipGroups });
}

function resolved(question: string) {
  const result = parse(question);
  if (result.status !== "resolved") {
    throw new Error(
      `expected "${question}" to resolve, got ${result.status}: ${"reason" in result ? result.reason : ""}`,
    );
  }
  return result.intent;
}

describe("the phrase lists", () => {
  it("only name chips that exist, in plain lowercase words", () => {
    for (const [id, phrases] of Object.entries(CHIP_PHRASES)) {
      expect(chipIds.has(id), id).toBe(true);
      for (const phrase of phrases) {
        expect(tokenize(phrase).join(" "), `${id}: ${phrase}`).toBe(phrase);
      }
    }
    for (const [phrase, ids] of Object.entries(CHIP_COMBO_PHRASES)) {
      expect(tokenize(phrase).join(" ")).toBe(phrase);
      ids.forEach((id) => expect(chipIds.has(id), id).toBe(true));
    }
  });

  it("never give one phrase to two chips or two stats' aliases", () => {
    const owner = new Map<string, string>();
    const claims: [string, string][] = [
      ...Object.entries(CHIP_PHRASES).flatMap(([id, ps]) => ps.map((p): [string, string] => [p, `chip ${id}`])),
      ...Object.keys(CHIP_COMBO_PHRASES).map((p): [string, string] => [p, "combo"]),
      ...STAT_DEFINITIONS.flatMap((s) =>
        s.aliases.map((p): [string, string] => [tokenize(p).join(" "), `stat ${s.id}`]),
      ),
    ];
    for (const [phrase, who] of claims) {
      const previous = owner.get(phrase);
      expect(previous === undefined || previous === who, `"${phrase}": ${previous} and ${who}`).toBe(true);
      owner.set(phrase, who);
    }
  });
});

describe("parseRules resolves plain questions", () => {
  it("reads fantasy points as the league stat, in any of its phrasings", () => {
    expect(resolved("Bijan Robinson fantasy points per game in 2026")).toEqual({
      stat_ids: ["league_pts"],
      filter_ids: ["season-2026"],
      granularity: "per_game",
    });
    expect(resolved("Bijan Robinson league points in 2023").stat_ids).toEqual(["league_pts"]);
    expect(resolved("Bijan Robinson points in my league in 2023").stat_ids).toEqual(["league_pts"]);
  });

  it("does not let fantasy points narrow which player a name means", () => {
    // Josh Allen the QB and Keenan Allen the WR are both Allens; a league stat has no position.
    expect(resolved("Josh Allen fantasy points in 2023").stat_ids).toEqual(["league_pts"]);
    expect(parse("Josh Allen and Bijan Robinson fantasy points in 2023").status).toBe("resolved");
  });

  it("reads a stat and a season", () => {
    expect(resolved("Joe Burrow passing yards in 2022")).toEqual({
      stat_ids: ["pass_yards"],
      filter_ids: ["season-2022"],
      granularity: "total",
    });
  });

  it("reads per game, several seasons and several stats, in reading order", () => {
    expect(resolved("Patrick Mahomes passing yards and touchdowns per game in 2021 and 2022")).toEqual({
      stat_ids: ["pass_yards", "pass_tds"],
      filter_ids: ["season-2021", "season-2022"],
      granularity: "per_game",
    });
  });

  it("prefers the longest phrase, so 'yards per carry' is not 'yards' plus 'per carry'", () => {
    expect(resolved("Saquon Barkley yards per carry in 2022").stat_ids).toEqual(["ypc"]);
    expect(resolved("Travis Kelce yards after the catch in 2023").stat_ids).toEqual(["rec_yac"]);
  });

  it("uses per play for a rate stat when nothing else is said", () => {
    expect(resolved("Kyler Murray CPOE in 2023").granularity).toBe("per_play");
  });

  it("maps situation phrases to their chips", () => {
    expect(resolved("Dak Prescott completion percentage on third down in 2023").filter_ids).toEqual([
      "down-3",
      "season-2023",
    ]);
    expect(resolved("Derrick Henry rushing yards in the playoffs in 2023").filter_ids).toContain("stype-post");
    expect(resolved("Travis Kelce receiving yards at home in 2023").filter_ids).toContain("loc-home");
    expect(resolved("Jordan Love passing yards in the first half in 2023").filter_ids).toContain("gclk-first-half");
  });

  it("maps a combined phrase to both chips", () => {
    expect(resolved("Patrick Mahomes passing yards on 3rd and long in 2023").filter_ids).toEqual(
      expect.arrayContaining(["down-3", "ytg-long", "season-2023"]),
    );
  });

  it("lets 'total' stand for the default and ignores filler words", () => {
    expect(resolved("What was Joe Burrow's total passing yards in 2022?").granularity).toBe("total");
  });

  it("works with two players", () => {
    expect(resolved("Compare Mahomes and Josh Allen passing yards in 2023").stat_ids).toEqual(["pass_yards"]);
  });
});

describe("a phrase two stats share", () => {
  it("is not guessed at: two stats are both labelled 'YAC share %'", () => {
    expect(parse("Travis Kelce YAC share % in 2023").status).toBe("ambiguous");
  });

  it("still reads a stat's own alias that is a shorter form of the shared label", () => {
    expect(resolved("Travis Kelce YAC share in 2023").stat_ids).toEqual(["rec_yac_share"]);
  });
});

describe("generic words need a clear role", () => {
  it("take the role of a stat named in the same question", () => {
    expect(resolved("Patrick Mahomes passing yards and touchdowns in 2023").stat_ids).toEqual([
      "pass_yards",
      "pass_tds",
    ]);
    expect(resolved("Derrick Henry rushing yards and touchdowns in 2023").stat_ids).toEqual(["rush_yards", "rush_tds"]);
  });

  it("take the passing role from a verb like 'throw'", () => {
    expect(resolved("How many touchdowns did Patrick Mahomes throw in 2023?").stat_ids).toEqual(["pass_tds"]);
    expect(resolved("How many passing touchdowns did Josh Allen throw in 2022?").stat_ids).toEqual(["pass_tds"]);
  });

  it("do not guess when a throwing verb meets a rushing stat", () => {
    expect(parse("How many rushing yards and touchdowns did Lamar Jackson throw for in 2023").status).not.toBe(
      "resolved",
    );
  });

  it("do not guess when the named stats disagree, or when a receiver asks for touchdowns", () => {
    expect(parse("Patrick Mahomes passing yards and rushing touchdowns and yards in 2023").status).not.toBe("resolved");
    expect(parse("Travis Kelce receiving yards and touchdowns in 2023").status).toBe("ambiguous");
  });

  it("reads 'yards' as receiving yards for a receiver", () => {
    expect(resolved("Travis Kelce yards in 2023").stat_ids).toEqual(["rec_yards"]);
  });

  it("does not guess for a quarterback or a running back, who both throw/catch and run", () => {
    for (const question of [
      "Patrick Mahomes yards in 2023",
      "Saquon Barkley yards in 2023",
      "Patrick Mahomes touchdowns in 2023",
    ]) {
      expect(parse(question).status, question).toBe("ambiguous");
    }
  });

  it("does not guess when the names disagree on role", () => {
    expect(parse("Patrick Mahomes and Travis Kelce yards in 2023").status).toBe("ambiguous");
  });
});

describe("parseRules does not misread joins and contrasts", () => {
  it("does not treat 'with' as a comparison of two players", () => {
    expect(parse("Patrick Mahomes passing yards with Travis Kelce in 2023").status).toBe("ambiguous");
  });

  it("does not take a number that is not a season for a missing season", () => {
    expect(parse("Did Derrick Henry reach 2000 rushing yards").status).toBe("ambiguous");
    expect(parse("Joe Burrow passing yards in 2000").status).toBe("unsupported");
  });

  it("does not merge a contrast into one query: home vs away, regular season vs playoffs", () => {
    expect(parse("Travis Kelce receiving yards at home vs away in 2023").status).toBe("ambiguous");
    expect(parse("Patrick Mahomes passing yards in the regular season vs the playoffs in 2023").status).toBe(
      "ambiguous",
    );
  });

  it("still combines chips from different groups and neighbouring downs", () => {
    expect(resolved("Patrick Mahomes passing yards on third down and in the red zone in 2023").filter_ids).toEqual(
      expect.arrayContaining(["down-3", "field-redzone"]),
    );
  });

  it("does not cross different players with different kinds of stat", () => {
    expect(parse("Patrick Mahomes passing yards and Travis Kelce receptions in 2023").status).toBe("ambiguous");
  });

  it("still compares players on the same kind of stat", () => {
    expect(resolved("Travis Kelce and George Kittle receptions per game in 2023").stat_ids).toEqual(["rec_receptions"]);
  });
});

/** Each question here once resolved to a query the user did not ask for. */
describe("parseRules regressions found in review", () => {
  const handedOver = (question: string, status: "ambiguous" | "unsupported" = "ambiguous") =>
    expect(parse(question).status, question).toBe(status);

  it("does not turn a year range into its two end years", () => {
    handedOver("Patrick Mahomes passing yards 2020-2023");
    handedOver("Patrick Mahomes passing yards 2021–2023");
    handedOver("Patrick Mahomes passing yards in 2022-23");
  });

  it("does not merge a comparison of seasons, filters or groups into one union query", () => {
    handedOver("Patrick Mahomes passing yards 2022 vs 2023");
    handedOver("Patrick Mahomes passing yards 2023 versus 2022");
    handedOver("Patrick Mahomes passing yards early season vs late season in 2023");
    handedOver("Patrick Mahomes passing yards first quarter vs fourth quarter in 2023");
    handedOver("Patrick Mahomes passing yards third down vs fourth down in 2023");
  });

  it("still reads vs and compare between two players", () => {
    expect(resolved("Travis Kelce vs George Kittle receptions in 2023").stat_ids).toEqual(["rec_receptions"]);
    expect(resolved("Compare Travis Kelce and George Kittle receptions in 2023").stat_ids).toEqual(["rec_receptions"]);
  });

  it("does not give every player the seasons or filters meant for one", () => {
    handedOver("Patrick Mahomes 2022 vs Jalen Hurts 2023 passing yards");
    handedOver("Patrick Mahomes passing yards 2023 and Jalen Hurts passing yards 2022");
  });

  it("does not turn a count into a per-play value when counting and rate stats are mixed", () => {
    handedOver("Patrick Mahomes passing yards and completion percentage in 2023");
    handedOver("Patrick Mahomes passing touchdowns and sack rate in 2023");
    expect(resolved("Patrick Mahomes passing yards and completion percentage per play in 2023").granularity).toBe(
      "per_play",
    );
  });

  it("reads 'interceptions' and 'picks' as the count, not the rate", () => {
    expect(resolved("Patrick Mahomes interceptions in 2023").stat_ids).toEqual(["pass_int"]);
    expect(resolved("Patrick Mahomes interception rate in 2023").stat_ids).toEqual(["int_rate"]);
  });

  it("does not read a bare 'sack', 'catch' or 'comp' as a percentage alias", () => {
    for (const question of [
      "Patrick Mahomes sack in 2023",
      "Travis Kelce catch in 2023",
      "Patrick Mahomes comp in 2023",
    ]) {
      expect(parse(question).status, question).not.toBe("resolved");
    }
    expect(resolved("Patrick Mahomes sack % in 2023").stat_ids).toEqual(["pass_sack_rate"]);
    expect(resolved("Patrick Mahomes completion % in 2023").stat_ids).toEqual(["cmp_pct"]);
  });

  it("does not read the half of a season as the half of a game", () => {
    handedOver("Patrick Mahomes passing yards in the first half of the season in 2023");
    handedOver("Patrick Mahomes passing yards second half of 2023");
    expect(resolved("Patrick Mahomes passing yards in the second half in 2023").filter_ids).toContain(
      "gclk-second-half",
    );
  });

  it("does not take a count after 'for' or 'and' for a missing season", () => {
    handedOver("Did Patrick Mahomes pass for 2000 yards in 2023");
    handedOver("Patrick Mahomes passing yards and 2000 attempts");
  });

  it("reads a name with a suffix as one name", () => {
    expect(resolved("Robert Henry Jr. rushing yards in 2023").stat_ids).toEqual(["rush_yards"]);
  });

  it("does not answer 'total yards' for a receiver, who may also run", () => {
    handedOver("Travis Kelce total yards in 2023");
  });

  it("does not pin a second player who cannot have the stat as a comparison", () => {
    handedOver("Patrick Mahomes passing yards versus Travis Kelce in 2023");
  });

  it("does not read 'in a season' as a season-less career total", () => {
    handedOver("Patrick Mahomes passing yards in a season");
    handedOver("Patrick Mahomes passing yards season");
  });

  it("copes with a data set that has no seasons", () => {
    const result = parseRules("Patrick Mahomes passing yards in 2023", {
      matches: resolvePlayers("Patrick Mahomes passing yards in 2023", PLAYERS),
      seasons: [],
      chipGroups,
    });

    expect(result.status).toBe("unknown");
  });
});

describe("parseRules hands over what it does not fully understand", () => {
  it("defers when a word is left over, and names it", () => {
    const result = parse("Patrick Mahomes net yards per attempt in 2023");

    expect(result).toMatchObject({ status: "ambiguous" });
    expect(JSON.stringify(result)).toContain("net");
  });

  it("defers on opponent, leaderboard and unknown-filter wording", () => {
    for (const question of [
      "Patrick Mahomes passing yards against the Chiefs in 2023",
      "Josh Allen passing yards in the last two minutes of games in 2023",
      "Lamar Jackson total yards in 2023",
    ]) {
      expect(parse(question).status, question).toBe("ambiguous");
    }
  });

  it("lists the words it did not understand, for whoever answers next", () => {
    expect(parse("Patrick Mahomes net yards per attempt in 2023")).toMatchObject({
      status: "ambiguous",
      unrecognized: ["net", "per", "attempt"],
    });
  });

  it("says unknown when no stat is named", () => {
    expect(parse("Patrick Mahomes in 2023").status).toBe("unknown");
  });

  it("says unknown when no player was matched", () => {
    expect(parseRules("passing yards in 2023", { matches: [], seasons: FIXTURE_SEASONS, chipGroups }).status).toBe(
      "unknown",
    );
  });

  it("refuses a season the data does not have, saying which seasons it has", () => {
    const result = parse("Joe Burrow passing yards in 2019");

    expect(result.status).toBe("unsupported");
    expect(JSON.stringify(result)).toMatch(/2021.*2026/);
  });

  it("defers when per game or total is asked of a rate stat", () => {
    expect(parse("Joe Burrow sack rate per game in 2023").status).toBe("ambiguous");
  });

  it("defers when per game and per play are both asked", () => {
    expect(parse("Joe Burrow passing yards per game per play in 2023").status).toBe("ambiguous");
  });

  it("defers when more stats are named than a query can hold", () => {
    expect(parse("Joe Burrow passing yards, passing touchdowns, sack rate, CPOE, EPA and ANY/A in 2023").status).toBe(
      "ambiguous",
    );
  });
});

describe("leaderboard questions with no player named", () => {
  function board(question: string) {
    const result = parse(question);
    if (result.status !== "resolved" || !result.leaderboard) {
      throw new Error(`expected "${question}" to be a leaderboard, got ${result.status}`);
    }
    return { intent: result.intent, ...result.leaderboard };
  }

  it("reads who led the league in a stat in a season", () => {
    const answer = board("Who led the league in passing yards in 2023");

    expect(answer.intent).toEqual({ stat_ids: ["pass_yards"], filter_ids: ["season-2023"], granularity: "total" });
    expect(answer.order).toEqual({ metric: "pass_yards", direction: "desc" });
    expect(answer.limit).toBe(10);
    expect(answer.minPlays).toBe(0);
  });

  it("reads top N as the limit", () => {
    const answer = board("top 5 rushing yards in 2022");

    expect(answer.intent.stat_ids).toEqual(["rush_yards"]);
    expect(answer.limit).toBe(5);
  });

  it("reads who has the most of a counting stat", () => {
    expect(board("Who has the most receptions in 2023").order.metric).toBe("rec_receptions");
  });

  it.each([
    ["fewest passing touchdowns in 2023", "pass_tds"],
    ["lowest interception rate in 2023", "int_rate"],
    ["who had the least rushing yards in 2022", "rush_yards"],
  ])("ranks lowest first for %s", (question, metric) => {
    expect(board(question).order).toEqual({ metric, direction: "asc" });
  });

  it.each(["lowest 5 sack rate in 2023", "fewest 5 passing touchdowns in 2023"])(
    "reads the number after %s as the limit",
    (question) => {
      const answer = board(question);

      expect(answer.order.direction).toBe("asc");
      expect(answer.limit).toBe(5);
    },
  );

  it("does not read at least as a lowest-first ranking", () => {
    expect(parse("who has at least 1000 rushing yards in 2023").status).not.toBe("resolved");
  });

  it("reads bottom N as a lowest-first limit", () => {
    const answer = board("bottom 5 rushing yards in 2023");

    expect(answer.order.direction).toBe("asc");
    expect(answer.limit).toBe(5);
  });

  it("keeps the play floor on a lowest-first rate ranking, or a one-play passer would top it", () => {
    expect(board("lowest interception rate in 2023").minPlays).toBeGreaterThan(0);
  });

  it.each([
    ["best completion percentage in 2023", "desc"],
    ["worst completion percentage in 2023", "asc"],
    ["best interception rate in 2023", "asc"],
    ["worst interception rate in 2023", "desc"],
  ])("reads %s by which way the stat is better", (question, direction) => {
    expect(board(question).order.direction).toBe(direction);
  });

  it("asks for a minimum number of plays on a rate, so one-play players cannot top it", () => {
    const answer = board("highest completion percentage in 2023");

    expect(answer.intent.granularity).toBe("per_play");
    expect(answer.minPlays).toBeGreaterThan(0);
  });

  it("asks for a minimum number of plays on a per game leaderboard", () => {
    const answer = board("top 10 passing yards per game in 2023");

    expect(answer.intent.granularity).toBe("per_game");
    expect(answer.minPlays).toBeGreaterThan(0);
  });

  it("covers every season when none is named", () => {
    expect(board("who led the league in passing touchdowns").intent.filter_ids).toEqual([]);
  });

  it("is not a leaderboard when a player is named", () => {
    const result = parse("Patrick Mahomes passing yards in 2023");

    expect(result.status).toBe("resolved");
    expect(result.status === "resolved" && result.leaderboard).toBeFalsy();
  });

  it.each([
    ["no leaderboard cue", "passing yards in 2023"],
    ["a bare yards that could be passing, rushing or receiving", "who led the league in yards in 2023"],
    ["a word it does not know", "top passers in 2023"],
    ["best for a stat with no better direction", "best adot in 2023"],
    ["both most and fewest", "most and fewest passing yards in 2023"],
    ["a limit over 100", "top 200 passing yards in 2023"],
    ["a limit of zero", "top 0 passing yards in 2023"],
  ])("hands over a question with %s", (_why, question) => {
    expect(["ambiguous", "unknown"]).toContain(parse(question).status);
    expect(parse(question).status === "resolved").toBe(false);
  });

  it("refuses a season the data does not have", () => {
    expect(parse("who led the league in passing yards in 2019").status).toBe("unsupported");
  });
});

describe("splitting by season or week", () => {
  it.each([
    ["Patrick Mahomes passing yards by season", "season"],
    ["Patrick Mahomes passing yards each season", "season"],
    ["Patrick Mahomes passing yards every year", "season"],
    ["Patrick Mahomes passing yards season by season", "season"],
    ["Patrick Mahomes passing yards by week in 2023", "week"],
    ["Patrick Mahomes passing yards each game in 2023", "week"],
    ["Patrick Mahomes passing yards game by game in 2023", "week"],
    ["Patrick Mahomes passing yards in 2023", null],
    ["Patrick Mahomes passing yards per game in 2023", null],
    ["Patrick Mahomes passing yards per season", "season"],
    ["Patrick Mahomes passing yards by week 5 in 2023", null],
  ])("reads %s as a %s split", (question, split) => {
    expect(splitAsked(question)).toBe(split);
  });

  it("reads the split words as understood, so the rest of the question still resolves", () => {
    const result = parse("Patrick Mahomes passing yards by season");

    expect(result.status).toBe("resolved");
    expect(result.status === "resolved" && result.intent).toEqual({
      stat_ids: ["pass_yards"],
      filter_ids: [],
      granularity: "total",
    });
  });

  it("does not read week 5 as a split; there is no single-week filter, so it is handed over", () => {
    expect(parse("Patrick Mahomes passing yards by week 5 in 2023").status).not.toBe("resolved");
  });

  it("asks a weekly leaderboard for a single game's worth of plays, not a season's", () => {
    const result = parse("top 5 completion percentage by week in 2023");

    expect(result.status === "resolved" && result.leaderboard?.minPlays).toBe(10);
  });

  it("hands over a question that asks for both splits", () => {
    expect(splitAsked("Patrick Mahomes passing yards by season and by week")).toBe("both");
    expect(parse("Patrick Mahomes passing yards by season and by week").status).toBe("ambiguous");
  });
});

describe("team questions", () => {
  function team(question: string) {
    const result = parse(question);
    if (result.status !== "resolved" || !result.team) {
      throw new Error(
        `expected "${question}" to be a team question, got ${result.status}: ${"reason" in result ? result.reason : ""}`,
      );
    }
    return { intent: result.intent, team: result.team, leaderboard: result.leaderboard };
  }

  it("reads a team's offense", () => {
    const answer = team("Chiefs passing yards in 2023");

    expect(answer.team).toEqual({ ids: ["KC"], side: "offense" });
    expect(answer.intent).toEqual({ stat_ids: ["pass_yards"], filter_ids: ["season-2023"], granularity: "total" });
  });

  it.each([
    "passing yards allowed by the Chiefs in 2023",
    "Chiefs defense passing yards in 2023",
    "passing yards against the Chiefs in 2023",
  ])("reads %s as the defense", (question) => {
    expect(team(question).team).toEqual({ ids: ["KC"], side: "defense" });
  });

  it("compares two teams", () => {
    expect(team("Chiefs and Bills rushing yards in 2023").team.ids).toEqual(["KC", "BUF"]);
  });

  it("ranks every team when it asks which team", () => {
    const answer = team("which team allowed the fewest passing yards in 2023");

    expect(answer.team).toEqual({ ids: [], side: "defense" });
    expect(answer.leaderboard?.order).toEqual({ metric: "pass_yards", direction: "asc" });
  });

  it("hands over a question that names a player and a team", () => {
    expect(parse("Patrick Mahomes passing yards against the Chiefs in 2023").status).not.toBe("resolved");
  });

  it("hands over a question that asks for offense and defense at once", () => {
    expect(parse("Chiefs offense and defense passing yards in 2023").status).toBe("ambiguous");
  });

  it("refuses a Next Gen Stat for a team", () => {
    expect(parse("Chiefs time to throw in 2023").status).toBe("unsupported");
  });
});

describe("team names inside player names", () => {
  const BILLS = {
    ...PLAYERS.find((p) => p.position === "QB")!,
    gsis_id: "00-0099999",
    display_name: "Keaton Bills",
    search_key: "keaton bills",
  };
  const withBills = (question: string) =>
    parseRules(question, {
      matches: resolvePlayers(question, [...PLAYERS, BILLS]),
      seasons: FIXTURE_SEASONS,
      chipGroups,
    });

  it("reads a player named in full even when the surname is a team's nickname", () => {
    const result = withBills("Keaton Bills passing yards in 2023");

    expect(result.status).toBe("resolved");
    expect(result.status === "resolved" && result.team).toBeUndefined();
  });

  it("does not make a player question about teams because it says team", () => {
    expect(parse("Patrick Mahomes team time to throw in 2023").status).not.toBe("unsupported");
  });

  it("asks a team ranking for no play floor, since every team has plenty", () => {
    const result = parse("which team had the highest completion percentage in 2023");

    expect(result.status === "resolved" && result.leaderboard?.minPlays).toBe(0);
  });
});
