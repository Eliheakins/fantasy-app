import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { buildFilterChipGroups, CHIP_COMBO_PHRASES, CHIP_PHRASES } from "@/shared/config/queryBuilderOptions";
import { STAT_DEFINITIONS } from "@/shared/config/statDictionary";
import type { PlayerDictionaryRow } from "@/shared/lib/schemas/players";
import { FIXTURE_SEASONS } from "@/test/seasons";

import { resolvePlayers, tokenize } from "./resolvePlayers";
import { parseRules } from "./ruleParser";

const PLAYERS = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../../backend/tests/eval/players.fixture.json", import.meta.url)), "utf8"),
) as PlayerDictionaryRow[];

const chipGroups = buildFilterChipGroups(FIXTURE_SEASONS);
const chipIds = new Set(chipGroups.flatMap((g) => g.options.map((o) => o.id)));

function parse(question: string) {
  return parseRules(question, { matches: resolvePlayers(question, PLAYERS), seasons: FIXTURE_SEASONS, chipGroups });
}

function resolved(question: string) {
  const result = parse(question);
  if (result.status !== "resolved") {
    throw new Error(`expected "${question}" to resolve, got ${result.status}: ${"reason" in result ? result.reason : ""}`);
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
      ...STAT_DEFINITIONS.flatMap((s) => s.aliases.map((p): [string, string] => [tokenize(p).join(" "), `stat ${s.id}`])),
    ];
    for (const [phrase, who] of claims) {
      const previous = owner.get(phrase);
      expect(previous === undefined || previous === who, `"${phrase}": ${previous} and ${who}`).toBe(true);
      owner.set(phrase, who);
    }
  });
});

describe("parseRules resolves plain questions", () => {
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
  it("is not guessed at: two stats are both labelled 'YAC share'", () => {
    expect(parse("Travis Kelce YAC share in 2023").status).not.toBe("resolved");
  });
});

describe("generic words need a clear role", () => {
  it("take the role of a stat named in the same question", () => {
    expect(resolved("Patrick Mahomes passing yards and touchdowns in 2023").stat_ids).toEqual(["pass_yards", "pass_tds"]);
    expect(resolved("Derrick Henry rushing yards and touchdowns in 2023").stat_ids).toEqual(["rush_yards", "rush_tds"]);
  });

  it("take the passing role from a verb like 'throw'", () => {
    expect(resolved("How many touchdowns did Patrick Mahomes throw in 2023?").stat_ids).toEqual(["pass_tds"]);
    expect(resolved("How many passing touchdowns did Josh Allen throw in 2022?").stat_ids).toEqual(["pass_tds"]);
  });

  it("do not guess when a throwing verb meets a rushing stat", () => {
    expect(parse("How many rushing yards and touchdowns did Lamar Jackson throw for in 2023").status).not.toBe("resolved");
  });

  it("do not guess when the named stats disagree, or when a receiver asks for touchdowns", () => {
    expect(parse("Patrick Mahomes passing yards and rushing touchdowns and yards in 2023").status).not.toBe("resolved");
    expect(parse("Travis Kelce receiving yards and touchdowns in 2023").status).toBe("ambiguous");
  });

  it("reads 'yards' as receiving yards for a receiver", () => {
    expect(resolved("Travis Kelce yards in 2023").stat_ids).toEqual(["rec_yards"]);
  });

  it("does not guess for a quarterback or a running back, who both throw/catch and run", () => {
    for (const question of ["Patrick Mahomes yards in 2023", "Saquon Barkley yards in 2023", "Patrick Mahomes touchdowns in 2023"]) {
      expect(parse(question).status, question).toBe("ambiguous");
    }
  });

  it("does not guess when the names disagree on role", () => {
    expect(parse("Patrick Mahomes and Travis Kelce yards in 2023").status).toBe("ambiguous");
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
      expect(parse(question).status, question).not.toBe("resolved");
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
    expect(parseRules("passing yards in 2023", { matches: [], seasons: FIXTURE_SEASONS, chipGroups }).status).toBe("unknown");
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
    expect(
      parse("Joe Burrow passing yards, passing touchdowns, sack rate, CPOE, EPA and ANY/A in 2023").status,
    ).toBe("ambiguous");
  });
});
