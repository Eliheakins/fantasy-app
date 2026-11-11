import { describe, expect, it, vi } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import type { IntentOutcome } from "@/stat/lib/schemas/nlqIntent";
import { FIXTURE_SEASONS } from "@/stat/testing/seasons";

import { readFantasyRoute } from "./fantasyRoute";
import { interpretQuestion } from "./interpretQuestion";
import { readRoster } from "./rosterWords";
import { tokenize } from "./resolvePlayers";
import { parseRules } from "./ruleParser";

const read = (q: string) => readRoster(tokenize(q));
const chipGroups = buildFilterChipGroups(FIXTURE_SEASONS);

describe("free agent rankings", () => {
  it("reads the issue's example as a WR ranking of free agents over the last 3 games", () => {
    const result = parseRules("free-agent WRs with the most targets over the last 3 games", {
      matches: [],
      seasons: FIXTURE_SEASONS,
      chipGroups,
    });

    expect(result.status).toBe("resolved");
    if (result.status === "resolved") {
      expect(result.leaderboard).toMatchObject({ position: "WR", roster: "fa" });
    }
  });

  it("refuses a team ranking narrowed to free agents", () => {
    const result = parseRules("which team has the most passing yards free agents", { matches: [], seasons: FIXTURE_SEASONS, chipGroups });

    expect(result.status).not.toBe("resolved");
  });

  it("never sends the model a roster word", async () => {
    const askModel = vi.fn<(q: string) => Promise<IntentOutcome>>().mockResolvedValue({
      outcome: "query",
      intent: { stat_ids: ["targets"], filter_ids: ["season-2023"], granularity: "total" },
    });

    await interpretQuestion({
      question: "free agent WRs with the most targets glorbnatzed",
      matches: [],
      seasons: FIXTURE_SEASONS,
      chipGroups,
      askModel,
    });

    expect(askModel).toHaveBeenCalledOnce();
    expect(askModel.mock.calls[0]![0]).not.toMatch(/free|agent/);
  });
});

describe("readRoster", () => {
  it("reads free agents, however it is written", () => {
    expect(read("free agent WRs with the most targets").roster).toBe("fa");
    expect(read("free-agent WRs with the most targets").roster).toBe("fa");
    expect(read("unrostered TEs with the most targets").roster).toBe("fa");
  });

  it("reads my roster and every roster", () => {
    expect(read("most targets on my roster").roster).toBe("mine");
    expect(read("my players with the most targets").roster).toBe("mine");
    expect(read("rostered WRs with the most targets").roster).toBe("rostered");
  });

  it("returns the positions of the words it read", () => {
    expect(read("free agent WRs").at).toEqual([0, 1]);
    expect(read("most targets on my team").at).toEqual([2, 3, 4]);
  });

  it("reads nothing from a question with no roster words", () => {
    expect(read("WRs with the most targets")).toEqual({ roster: null, at: [] });
  });

  it("refuses two different roster groups", () => {
    expect(read("free agent and rostered WRs").reason).toBeDefined();
  });
});

describe("free agents and the Moves link", () => {
  const route = (q: string) => readFantasyRoute(q, []);

  it("still sends 'who should I add' style questions to Moves", () => {
    expect(route("who are the best free agents")?.to).toBe("/moves?view=fa");
    expect(route("top free agents")?.to).toBe("/moves?view=fa");
  });

  it("leaves a free-agent stat count to the stat paths", () => {
    expect(route("free agent WRs with the most targets over the last 3 games")).toBeNull();
    expect(route("which free agent has the fewest drops")).toBeNull();
  });

  it("keeps waivers and pick-ups on Moves even when a count is named", () => {
    expect(route("who has the most targets on waivers")?.to).toBe("/moves?view=fa");
  });
});
