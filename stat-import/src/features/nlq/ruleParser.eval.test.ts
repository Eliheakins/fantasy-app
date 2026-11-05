/**
 * Guards the rules parser against silent wrong answers. Runs every eval question (the 44 known
 * cases, the held-out set written before the parser, and the corrections users made) through it. See `npm run eval:rules` for the
 * printable report. The numbers it must keep up are floors, set a little under what it scores today.
 */
import { describe, expect, it } from "vitest";

import { FIXTURE_SEASONS } from "@/test/seasons";

import { runRulesEval } from "./ruleEval";

const rows = runRulesEval(FIXTURE_SEASONS);

describe("rules parser against the eval questions", () => {
  it("never answers wrongly: a question is resolved correctly, refused, or handed to the model", () => {
    const wrong = rows.filter((r) => r.verdict === "wrong").map((r) => r.case.q);

    expect(wrong).toEqual([]);
  });

  it("never resolves a question that should be refused or deferred", () => {
    const guessed = rows
      .filter(
        (r) =>
          (r.case.unsupported || r.case.rules === "defer") &&
          r.case.rules !== "leaderboard" &&
          r.result.status === "resolved",
      )
      .map((r) => r.case.q);

    expect(guessed).toEqual([]);
  });

  it.each(["cases", "heldout"] as const)("answers most answerable questions in %s itself", (set) => {
    const answerable = rows.filter((r) => r.set === set && !r.case.unsupported && r.case.rules !== "defer");
    const correct = answerable.filter((r) => r.verdict === "correct");

    expect(answerable.length).toBeGreaterThan(20);
    expect(correct.length / answerable.length).toBeGreaterThanOrEqual(0.9);
  });

  it("covers the written question sets", () => {
    const sets = new Set(rows.map((r) => r.set));

    expect(sets.has("cases") && sets.has("heldout")).toBe(true);
  });
});
