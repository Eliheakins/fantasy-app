/**
 * Scores the rules parser against the eval questions (`backend/tests/eval/cases.json`, `heldout.json`
 * and `corrections.json`, the questions a user had to fix). Shared by the CI test and the printable report (`npm run eval:rules`).
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { buildFilterChipGroups } from "@/shared/config/queryBuilderOptions";
import type { PlayerDictionaryRow } from "@/shared/lib/schemas/players";
import type { GranularityMode } from "@/shared/types/queryBuilder";

import { resolvePlayers } from "./resolvePlayers";
import { dropTeamNames, resolveTeams } from "./resolveTeams";
import { parseRules, type RuleResult } from "./ruleParser";

export interface EvalCase {
  q: string;
  stats?: string[];
  filters?: string[];
  /** null means the case does not check it. */
  granularity?: GranularityMode | null;
  /** The question must be refused. */
  unsupported?: boolean;
  /** "defer": the rules parser must hand this one over rather than guess. "leaderboard": it must read it as a league ranking of `stats` and `filters`. */
  rules?: "defer" | "leaderboard";
  trap?: string;
}

/**
 * correct: resolved to the expected query, or refused a question that should be refused.
 * deferred: handed to the model. wrong: answered a question it should not have, or answered it differently.
 */
export type Verdict = "correct" | "deferred" | "wrong";

const sameSet = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((x) => b.includes(x));

export function judge(c: EvalCase, result: RuleResult): Verdict {
  if (result.status === "ambiguous" || result.status === "unknown") {
    return "deferred";
  }
  if (result.status === "unsupported") {
    return c.unsupported ? "correct" : "wrong";
  }
  const { intent } = result;
  if (c.rules === "leaderboard") {
    const reads =
      result.leaderboard && sameSet(intent.stat_ids, c.stats ?? []) && sameSet(intent.filter_ids, c.filters ?? []);
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

const EVAL_DIR = fileURLToPath(new URL("../../../../backend/tests/eval/", import.meta.url));
const readJson = <T>(name: string): T => JSON.parse(readFileSync(`${EVAL_DIR}${name}`, "utf8")) as T;

export const EVAL_SETS = ["cases", "heldout", "corrections"] as const;

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
