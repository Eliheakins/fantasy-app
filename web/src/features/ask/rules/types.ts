import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import type { QueryIntent } from "@/stat/lib/schemas/nlqIntent";
import type { Side } from "@/stat/types/queryBuilder";

import type { Leaderboard } from "../ranking";
import type { PlayerMatch } from "../resolvePlayers";

export interface RuleContext {
  /** Players already found in the question (their words are not part of the stat wording). */
  matches: readonly PlayerMatch[];
  /** Seasons the data has. */
  seasons: readonly number[];
  chipGroups: readonly FilterChipGroup[];
  /** The latest week each season reaches, for "last week" and "since week 5". */
  maxWeeks?: Readonly<Record<number, number>>;
}

export type RuleResult =
  /** `team`: the question is about teams (none named means a ranking of all 32). */
  | { status: "resolved"; intent: QueryIntent; leaderboard?: Leaderboard; team?: { ids: string[]; side: Side } }
  /** A question the data cannot answer, said with certainty (a season it does not have). */
  | { status: "unsupported"; reason: string }
  /** Understood in part; the wording leaves a real choice open. `unrecognized` lists words it could not place. */
  | { status: "ambiguous"; reason: string; unrecognized?: string[] }
  | { status: "unknown"; reason: string };

/** What one parsing stage hands on: its typed partial, or the final answer when it settles the question. */
export type Stage<T> = { ok: true; value: T } | { ok: false; result: RuleResult };

export const proceed = <T>(value: T): Stage<T> => ({ ok: true, value });
export const stop = (result: RuleResult): Stage<never> => ({ ok: false, result });

export const ambiguous = (reason: string, unrecognized?: string[]): RuleResult =>
  unrecognized ? { status: "ambiguous", reason, unrecognized } : { status: "ambiguous", reason };

/** Which words of the question are accounted for. Built up in place by the stages of one parse. */
export type WordMask = boolean[];
