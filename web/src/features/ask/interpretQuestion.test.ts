import { describe, expect, it, vi } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import type { IntentOutcome } from "@/stat/lib/schemas/nlqIntent";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import { FIXTURE_SEASONS } from "@/stat/testing/seasons";

import { interpretQuestion } from "./interpretQuestion";
import { resolvePlayers } from "./resolvePlayers";

const row = (gsis_id: string, name: string, position: string): PlayerDictionaryRow => ({
  gsis_id,
  display_name: name,
  search_key: name.toLowerCase(),
  position,
  team: "KC",
});
const PLAYERS = [row("m", "Patrick Mahomes", "QB"), row("k", "Travis Kelce", "TE")];

const MODEL_INTENT: IntentOutcome = {
  outcome: "query",
  intent: { stat_ids: ["pass_tds"], filter_ids: ["season-2023"], granularity: "total" },
};

function interpret(question: string, askModel: (q: string) => Promise<IntentOutcome>) {
  return interpretQuestion({
    question,
    matches: resolvePlayers(question, PLAYERS),
    seasons: FIXTURE_SEASONS,
    chipGroups: buildFilterChipGroups(FIXTURE_SEASONS),
    askModel,
  });
}

describe("interpretQuestion", () => {
  it("answers with the rules when they understand the question, and never calls the model", async () => {
    const askModel = vi.fn();

    const result = await interpret("Patrick Mahomes passing yards in 2023", askModel);

    expect(result).toEqual({
      kind: "intent",
      path: "rules",
      intent: { stat_ids: ["pass_yards"], filter_ids: ["season-2023"], granularity: "total" },
    });
    expect(askModel).not.toHaveBeenCalled();
  });

  it("refuses a season the data lacks without calling the model", async () => {
    const askModel = vi.fn();

    const result = await interpret("Patrick Mahomes passing yards in 2019", askModel);

    expect(result).toMatchObject({ kind: "message" });
    expect(askModel).not.toHaveBeenCalled();
  });

  it("hands a question the rules cannot read to the model", async () => {
    const askModel = vi.fn().mockResolvedValue(MODEL_INTENT);

    const result = await interpret("Patrick Mahomes touchdowns in 2023", askModel);

    expect(askModel).toHaveBeenCalledWith("Patrick Mahomes touchdowns in 2023");
    expect(result).toEqual({ kind: "intent", path: "model", intent: MODEL_INTENT.intent, unrecognized: [] });
  });

  it("tells the user which words the rules did not understand when the model answers instead", async () => {
    const askModel = vi.fn().mockResolvedValue(MODEL_INTENT);

    const result = await interpret("Patrick Mahomes passing yards against the Chiefs in 2023", askModel);

    expect(result).toMatchObject({ kind: "intent", path: "model", unrecognized: ["against", "chiefs"] });
  });

  it("has nothing to flag when the rules deferred for another reason", async () => {
    const askModel = vi.fn().mockResolvedValue(MODEL_INTENT);

    const result = await interpret("Patrick Mahomes touchdowns in 2023", askModel);

    expect(result).toMatchObject({ kind: "intent", path: "model", unrecognized: [] });
  });

  it("passes on the model's refusal as a message", async () => {
    const askModel = vi.fn().mockResolvedValue({ outcome: "unsupported", reason: "Salaries are not in the data." });

    const result = await interpret("Patrick Mahomes salary in 2023", askModel);

    expect(result).toEqual({ kind: "message", text: "Salaries are not in the data." });
  });

  it("says why neither could help when the model is unavailable, so Ask still explains itself", async () => {
    const askModel = vi.fn().mockRejectedValue(new Error("The Ask service is not reachable at http://localhost:8100."));

    const result = await interpret("Patrick Mahomes net yards per attempt in 2023", askModel);

    expect(result.kind).toBe("message");
    const text = result.kind === "message" ? result.text : "";
    expect(text).toContain("net");
    expect(text).toContain("not reachable");
  });
});
