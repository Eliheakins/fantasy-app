import type { Split } from "@/stat/types/queryBuilder";

import { readSingleGame } from "../ranking";
import { wordsOf, YEAR } from "./vocab";

/** "by season", "each game", "every year": a word that asks for a split, then the unit. */
const SPLIT_LEADS = new Set(["by", "each", "every", "per"]);
/** "per game" is a granularity, so "per" only splits by season. */
const PER_SPLITS = new Set(["season", "seasons", "year", "years"]);
const SPLIT_UNITS = new Map<string, Split>([
  ["season", "season"],
  ["seasons", "season"],
  ["year", "season"],
  ["years", "season"],
  ["week", "week"],
  ["weeks", "week"],
  ["game", "week"],
  ["games", "week"],
]);

/** Words that set two cases side by side ("home vs away", "2023 vs 2024"). */
const CONTRAST_JOINS = new Set(["vs", "versus", "and", "or"]);

export interface SplitRead {
  split: Split | "both" | null;
  /** Token indices of the words that asked for it. */
  at: number[];
}

/** Which split the words ask for, and where they are; "season by season" counts like "by season". */
export function findSplit(tokens: readonly string[]): SplitRead {
  const asked = new Set<Split>();
  const at: number[] = [];
  tokens.forEach((token, i) => {
    const next = tokens[i + 1] ?? "";
    const unit = SPLIT_UNITS.get(next);
    // "by week 5" names a week, not a split.
    const namesOne = /^\d+$/.test(tokens[i + 2] ?? "");
    if (SPLIT_LEADS.has(token) && unit && !namesOne && (token !== "per" || PER_SPLITS.has(next))) {
      asked.add(unit);
      at.push(i, i + 1);
      if (tokens[i - 1] !== undefined && SPLIT_UNITS.get(tokens[i - 1]!) === unit) {
        at.push(i - 1);
      }
    }
  });
  // "most passing yards in a single game" ranks single games: a split by week.
  const single = readSingleGame(tokens);
  if (single) {
    asked.add("week");
    at.push(...single);
  }
  // Two cases side by side: "2023 vs 2024" splits by season, "home vs away" by home and away.
  tokens.forEach((token, i) => {
    if (!CONTRAST_JOINS.has(token)) {
      return;
    }
    const [before, after] = [tokens[i - 1] ?? "", tokens[i + 1] ?? ""];
    const sides = new Set([before, after, tokens[i + 2] ?? ""]);
    if (YEAR.test(before) && YEAR.test(after) && token !== "and") {
      asked.add("season");
      at.push(i);
    } else if (before === "home" && (sides.has("away") || sides.has("road"))) {
      asked.add("location");
      at.push(i);
    }
  });
  return { split: asked.size > 1 ? "both" : ([...asked][0] ?? null), at };
}

/** The split a question asks for, whichever path reads the rest of it; "both" means it asks for two. */
export const splitAsked = (question: string): Split | "both" | null => findSplit(wordsOf(question)).split;
