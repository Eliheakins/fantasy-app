import { describe, expect, it } from "vitest";

import { metricSelectAlias } from "@/shared/lib/queryBuilder";

import { buildAnswer } from "./answerText";

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
      nameByGsis: NAMES,
      ranked: true,
    });

    expect(answer.lines).toEqual([
      "1. Patrick Mahomes — Pass yards (total): 4183",
      "2. Travis Kelce — Pass yards (total): 3000",
    ]);
  });
});
