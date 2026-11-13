/**
 * Start/sit questions ("start A or B", "A or B this week"), read by rules only: the model prompt and
 * catalog do not know about them. The answer comes from the lineup API, not from model text.
 */
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";

import { NAME_SUFFIXES, type PlayerMatch, pickCandidate, resolvePlayers, tokenize } from "./resolvePlayers";

export interface StartSitOutcome {
  kind: "start_sit";
  a: string;
  b: string;
}

export type StartSitRead =
  | { status: "none" }
  | { status: "message"; text: string }
  | { status: "choose"; sure: PlayerDictionaryRow[]; unsure: PlayerMatch[] }
  | { status: "resolved"; outcome: StartSitOutcome; names: Record<string, string> };

const LEAD = /^(?:(?:who\s+)?should\s+i\s+|who\s+(?:do\s+i|to)\s+)?(?:start|sit|play|bench)\b[:,]?\s+/i;
const THIS_WEEK = /\s+this\s+week$/i;
const SEPARATOR = /\s+(?:or|over|vs\.?|versus)\s+/i;

/** The question without surrounding space or trailing punctuation, as the start/sit and trade readers parse it. */
export const trimQuestion = (question: string): string => question.trim().replace(/[?!.\s]+$/, "");

export const notFoundMessage = (phrase: string): string => `I couldn't find a player called “${phrase}”. Use a last or full name.`;

/** Matches split into players settled without asking and namesakes the user must choose between. */
export function partitionPicks(matches: readonly PlayerMatch[]): { sure: PlayerDictionaryRow[]; unsure: PlayerMatch[] } {
  const sure: PlayerDictionaryRow[] = [];
  const unsure: PlayerMatch[] = [];
  for (const match of matches) {
    const pick = pickCandidate(match, []);
    if (pick) {
      sure.push(pick);
    } else {
      unsure.push(match);
    }
  }
  return { sure, unsure };
}

/** The two name phrases of a start/sit question, or null for any other question. */
export function parseStartSit(question: string): { a: string; b: string; hasVerb: boolean } | null {
  const text = trimQuestion(question);
  const hasVerb = LEAD.test(text);
  const hasWeek = THIS_WEEK.test(text);
  if (!hasVerb && !hasWeek) {
    return null;
  }
  const sides = text
    .replace(LEAD, "")
    .replace(THIS_WEEK, "")
    .split(SEPARATOR)
    .map((s) => s.trim());
  const [a, b] = sides;
  return sides.length === 2 && a && b ? { a, b, hasVerb } : null;
}

const words = (text: string) => tokenize(text).filter((t) => !NAME_SUFFIXES.has(t)).length;

/** One side as a single player match; "extra" means words beyond the name (a stat comparison), "none" no player. */
export function sideMatch(side: string, dict: readonly PlayerDictionaryRow[]): PlayerMatch | "extra" | "none" {
  const matches = resolvePlayers(side, dict);
  if (matches.length === 0) {
    return "none";
  }
  const only = matches.length === 1 ? matches[0]! : null;
  return only && words(only.phrase) === words(side) ? only : "extra";
}

export function readStartSit(question: string, dict: readonly PlayerDictionaryRow[]): StartSitRead {
  const sides = parseStartSit(question);
  if (!sides) {
    return { status: "none" };
  }
  const matches: PlayerMatch[] = [];
  for (const side of [sides.a, sides.b]) {
    const match = sideMatch(side, dict);
    // Words after a name ("Kittle receptions") make it a stat question: leave it to the stat path.
    if (match === "extra" || (match === "none" && !sides.hasVerb)) {
      return { status: "none" };
    }
    if (match === "none") {
      return { status: "message", text: notFoundMessage(side) };
    }
    matches.push(match);
  }
  const { sure, unsure } = partitionPicks(matches);
  return unsure.length > 0 ? { status: "choose", sure, unsure } : finishStartSit(sure);
}

/** The outcome once both players are settled (also after the user picks between namesakes). */
export function finishStartSit(players: readonly PlayerDictionaryRow[]): StartSitRead {
  const [a, b] = players;
  if (!a || !b) {
    return { status: "message", text: "A start/sit question needs two players." };
  }
  if (a.gsis_id === b.gsis_id) {
    return { status: "message", text: `That is the same player twice (${a.display_name}). Name two different players.` };
  }
  return {
    status: "resolved",
    outcome: { kind: "start_sit", a: a.gsis_id, b: b.gsis_id },
    names: { [a.gsis_id]: a.display_name, [b.gsis_id]: b.display_name },
  };
}
