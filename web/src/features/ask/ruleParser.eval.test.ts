/**
 * Guards the rules parser against silent wrong answers. Runs every eval question (the 44 known
 * cases, the held-out set written before the parser, and the corrections users made) through it.
 * The floors below are a little under what it scores; the last test pins the numbers the stat README states.
 */
import { describe, expect, it } from "vitest";

import { FIXTURE_SEASONS } from "@/stat/testing/seasons";

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
          !r.case.rules_reads &&
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

  it("matches the stat README's rules-eval numbers", () => {
    const answerable = (set: string) => rows.filter((r) => r.set === set && !r.case.unsupported && r.case.rules !== "defer");
    const of = (set: string, verdict: string, from = rows.filter((r) => r.set === set)) => from.filter((r) => r.verdict === verdict).length;

    // cases.json: 43/43 answerable correct (40/40 before the league points stat), 0 wrong.
    expect([of("cases", "correct", answerable("cases")), answerable("cases").length, of("cases", "wrong")]).toEqual([43, 43, 0]);
    // heldout.json: 28/28 answerable correct (one more deferred on purpose), 0 wrong, 1 trap refused, the opponent trap read
    // by the rules (rules_reads), 4 handed to the model
    // (25/25 and 7 before the interception count made "Justin Herbert interceptions in 2021" answerable; 26/26 before
    // the model could rank, which made the "Who led the league" case answerable rather than a model trap; 27/27 and 6
    // before yards per reception made "Travis Kelce yards per catch" answerable; 5 before opponents were read in code).
    const held = rows.filter((r) => r.set === "heldout");
    expect([of("heldout", "correct", answerable("heldout")), answerable("heldout").length, of("heldout", "wrong")]).toEqual([28, 28, 0]);
    expect(held.filter((r) => r.case.unsupported && r.result.status === "unsupported").length).toBe(1);
    expect(of("heldout", "deferred")).toBe(4);
    expect(held.filter((r) => r.case.rules_reads && r.verdict === "correct").length).toBe(1);
    expect(rows.filter((r) => r.set === "corrections" && r.verdict === "wrong")).toEqual([]);
  });

  it("covers the written question sets", () => {
    const sets = new Set(rows.map((r) => r.set));

    expect(sets.has("cases") && sets.has("heldout")).toBe(true);
  });
});
