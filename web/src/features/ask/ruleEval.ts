/**
 * Scores the rules parser against the eval questions (`tests/stat/eval/cases.json`, `heldout.json`
 * and `corrections.json`, the questions a user had to fix). Used by ruleParser.eval.test.ts.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import type { GranularityMode } from "@/stat/types/queryBuilder";

import { resolvePlayers } from "./resolvePlayers";
import { dropTeamNames, resolveTeams } from "./resolveTeams";
import { parseRules, type RuleResult } from "./ruleParser";

interface EvalCase {
  q: string;
  stats?: string[];
  filters?: string[];
  /** null means the case does not check it. */
  granularity?: GranularityMode | null;
  /** The question must be refused. */
  unsupported?: boolean;
  /** "defer": the rules parser must hand this one over rather than guess. "leaderboard": it must read it as a league ranking of `stats` and `filters`. */
  rules?: "defer" | "leaderboard";
  /**
   * What the rules must read where the model alone must refuse: Ask reads some words in code before the
   * model is asked (opponents), so the model, sent the raw question in its eval, has no filter for them.
   */
  rules_reads?: { stats: string[]; filters: string[] };
  trap?: string;
}

/**
 * correct: resolved to the expected query, or refused a question that should be refused.
 * deferred: handed to the model. wrong: answered a question it should not have, or answered it differently.
 */
type Verdict = "correct" | "deferred" | "wrong";

const sameSet = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((x) => b.includes(x));

function judge(c: EvalCase, result: RuleResult): Verdict {
  if (result.status === "ambiguous" || result.status === "unknown") {
    return "deferred";
  }
  if (result.status === "unsupported") {
    return c.unsupported && !c.rules_reads ? "correct" : "wrong";
  }
  const { intent } = result;
  if (c.rules_reads) {
    const reads = sameSet(intent.stat_ids, c.rules_reads.stats) && sameSet(intent.filter_ids, c.rules_reads.filters);
    return reads ? "correct" : "wrong";
  }
  if (c.rules === "leaderboard") {
    const reads = result.leaderboard && sameSet(intent.stat_ids, c.stats ?? []) && sameSet(intent.filter_ids, c.filters ?? []);
    return reads ? "correct" : "wrong";
  }
  if (c.unsupported || c.rules === "defer") {
    return "wrong";
  }
  const matches =
    sameSet(intent.stat_ids, c.stats ?? []) &&
    sameSet(intent.filter_ids, c.filters ?? []) &&
    (c.granularity == null || intent.granularity === c.granularity);
  return matches ? "correct" : "wrong";
}

const EVAL_DIR = resolve(import.meta.dirname, "../../../../tests/stat/eval");
const readJson = <T>(name: string): T => JSON.parse(readFileSync(resolve(EVAL_DIR, name), "utf8")) as T;

const EVAL_SETS = ["cases", "heldout", "corrections"] as const;

export interface EvalRow {
  set: (typeof EVAL_SETS)[number];
  case: EvalCase;
  result: RuleResult;
  verdict: Verdict;
}

export function runRulesEval(seasons: readonly number[]): EvalRow[] {
  const players = readJson<PlayerDictionaryRow[]>("players.fixture.json");
  const chipGroups = buildFilterChipGroups(seasons);

  return EVAL_SETS.flatMap((set) =>
    readJson<EvalCase[]>(`${set}.json`).map((c): EvalRow => {
      const matches = dropTeamNames(resolvePlayers(c.q, players), resolveTeams(c.q));
      const result = parseRules(c.q, { matches, seasons, chipGroups });
      return { set, case: c, result, verdict: judge(c, result) };
    }),
  );
}
