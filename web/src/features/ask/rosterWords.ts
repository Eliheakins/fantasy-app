/**
 * League roster words, read in code on every path: "free agent WRs", "on my roster", "rostered". They
 * set the Find players League filter (`lg`) and are cut from the text the model sees, so no league
 * word, and none of the league's data, reaches a model prompt.
 */
import type { RosterFilter } from "@/stat/lib/queryUrl";

/** Longest phrases first, so "on my roster" is one phrase and not "my roster" with a stray "on". */
const ROSTER_PHRASES: readonly [string[], RosterFilter][] = [
  [["on", "my", "roster"], "mine"],
  [["on", "my", "team"], "mine"],
  [["my", "roster"], "mine"],
  [["my", "players"], "mine"],
  [["free", "agents"], "fa"],
  [["free", "agent"], "fa"],
  [["unrostered"], "fa"],
  [["rostered"], "rostered"],
];

/** The roster group a question names, the positions of its words, and a reason when it names two. */
export function readRoster(tokens: readonly string[]): { roster: RosterFilter | null; at: number[]; reason?: string } {
  const at = new Set<number>();
  const found = new Set<RosterFilter>();
  for (const [words, roster] of ROSTER_PHRASES) {
    for (let i = 0; i + words.length <= tokens.length; i++) {
      const span = words.map((_, k) => i + k);
      if (words.every((w, k) => tokens[i + k] === w) && !span.some((p) => at.has(p))) {
        found.add(roster);
        span.forEach((p) => at.add(p));
      }
    }
  }
  const sorted = [...at].sort((a, b) => a - b);
  if (found.size > 1) {
    return { roster: null, at: sorted, reason: "It names more than one group of rostered players." };
  }
  return { roster: [...found][0] ?? null, at: sorted };
}
