import { describe, expect, it } from "vitest";

import {
  getStatById,
  getStatsByCategory,
  playerColumnForRole,
  STAT_CATEGORY_LABELS,
  STAT_CATEGORY_ORDER,
  STAT_DEFINITIONS,
} from "./statDictionary";

describe("stat dictionary", () => {
  it("loads every stat the app had from metrics.json", () => {
    expect(STAT_DEFINITIONS.length).toBeGreaterThanOrEqual(39);
    expect(new Set(STAT_DEFINITIONS.map((s) => s.id)).size).toBe(STAT_DEFINITIONS.length);
  });

  it("keeps the category order and labels", () => {
    expect(STAT_CATEGORY_ORDER[0]).toBe("passing");
    expect(STAT_CATEGORY_LABELS.passing).toBe("Passing");
    expect(STAT_CATEGORY_LABELS.ngs_receiving).toBe("NGS · Receiving");
  });

  it("maps the file's snake_case fields onto the shape the builder uses", () => {
    expect(getStatById("pass_yards")).toMatchObject({
      id: "pass_yards",
      label: "Pass yards",
      category: "passing",
      playerRole: "passer",
      playType: "pass",
      rate_only: false,
    });
  });

  it("returns undefined for an unknown or null id", () => {
    expect(getStatById("nope")).toBeUndefined();
    expect(getStatById(null)).toBeUndefined();
  });

  it("groups stats by category", () => {
    expect(getStatsByCategory("passing").length).toBeGreaterThan(0);
    expect(getStatsByCategory("passing").every((s) => s.category === "passing")).toBe(true);
  });

  it("gives every stat a person can ask for at least one alias", () => {
    expect(STAT_DEFINITIONS.filter((s) => s.aliases.length === 0 && !s.hidden)).toEqual([]);
  });

  it("names the play-by-play column for each role", () => {
    expect(playerColumnForRole("passer")).toBe("passer_player_id");
    expect(playerColumnForRole("rusher")).toBe("rusher_player_id");
    expect(playerColumnForRole("receiver")).toBe("receiver_player_id");
  });
});
