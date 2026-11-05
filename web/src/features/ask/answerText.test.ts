import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import { metricSelectAlias } from "@/stat/lib/queryBuilder";

import { FIXTURE_SEASONS } from "@/stat/testing/seasons";

import { buildAnswer } from "./answerText";

const CHIP_GROUPS = buildFilterChipGroups(FIXTURE_SEASONS);

const NAMES = new Map([
  ["m", "Patrick Mahomes"],
  ["k", "Travis Kelce"],
]);

const passYards = metricSelectAlias("pass_yards");
const passTds = metricSelectAlias("pass_tds");

describe("buildAnswer", () => {
  it("writes one line per player with each metric labelled by granularity", () => {
    const answer = buildAnswer({
      result: {
        columns: ["player_id", passYards, passTds],
        rows: [{ player_id: "m", [passYards]: 4183, [passTds]: 27 }],
      },
      statIds: ["pass_yards", "pass_tds"],
      granularity: "total",
      filterIds: ["season-2023"],
      chipGroups: CHIP_GROUPS,
      nameByGsis: NAMES,
    });

    expect(answer.context).toBe("2023");
    expect(answer.lines).toEqual(["Patrick Mahomes — Pass yards (total): 4183 · Pass TDs (total): 27"]);
  });

  it("prefixes non-season filters with their group and joins several", () => {
    const answer = buildAnswer({
      result: { columns: ["player_id", passYards], rows: [] },
      statIds: ["pass_yards"],
      granularity: "per_game",
      filterIds: ["season-2022", "stype-post", "down-3"],
      chipGroups: CHIP_GROUPS,
      nameByGsis: NAMES,
    });

    expect(answer.context).toBe("2022, Down: 3rd, Season type: Playoffs");
    expect(answer.lines).toEqual([]);
  });

  it("falls back to the player id and an em dash for missing values", () => {
    const answer = buildAnswer({
      result: { columns: ["player_id", passYards], rows: [{ player_id: "zz", [passYards]: null }] },
      statIds: ["pass_yards"],
      granularity: "total",
      filterIds: [],
      chipGroups: CHIP_GROUPS,
      nameByGsis: NAMES,
    });

    expect(answer.context).toBe("All loaded seasons");
    expect(answer.lines).toEqual(["zz — Pass yards (total): —"]);
  });
});

describe("buildAnswer for a leaderboard", () => {
  it("numbers the lines in the order of the rows", () => {
    const answer = buildAnswer({
      result: {
        columns: ["player_id", passYards],
        rows: [
          { player_id: "m", [passYards]: 4183 },
          { player_id: "k", [passYards]: 3000 },
        ],
      },
      statIds: ["pass_yards"],
      granularity: "total",
      filterIds: ["season-2023"],
      chipGroups: CHIP_GROUPS,
      nameByGsis: NAMES,
      ranked: true,
    });

    expect(answer.lines).toEqual([
      "1. Patrick Mahomes — Pass yards (total): 4183",
      "2. Travis Kelce — Pass yards (total): 3000",
    ]);
  });
});

describe("buildAnswer for a split", () => {
  it("names the season, or the season and week, on each line", () => {
    const answer = buildAnswer({
      result: {
        columns: ["player_id", "season", "week", passYards],
        rows: [
          { player_id: "m", season: 2023, week: 1, [passYards]: 226 },
          { player_id: "m", season: 2023, week: 2, [passYards]: 305 },
        ],
      },
      statIds: ["pass_yards"],
      granularity: "total",
      filterIds: ["season-2023"],
      chipGroups: CHIP_GROUPS,
      nameByGsis: NAMES,
    });

    expect(answer.lines).toEqual([
      "Patrick Mahomes, 2023 week 1 — Pass yards (total): 226",
      "Patrick Mahomes, 2023 week 2 — Pass yards (total): 305",
    ]);
  });
});

describe("buildAnswer for teams", () => {
  it("names each team row from its team_id", () => {
    const answer = buildAnswer({
      result: { columns: ["team_id", passYards], rows: [{ team_id: "KC", [passYards]: 4383 }] },
      statIds: ["pass_yards"],
      granularity: "total",
      filterIds: ["season-2023"],
      chipGroups: CHIP_GROUPS,
      nameByGsis: new Map([["KC", "Kansas City Chiefs"]]),
      idColumn: "team_id",
    });

    expect(answer.lines).toEqual(["Kansas City Chiefs — Pass yards (total): 4383"]);
  });
});
