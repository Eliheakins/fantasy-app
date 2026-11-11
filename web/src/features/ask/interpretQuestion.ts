import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import type { IntentOutcome, QueryIntent } from "@/stat/lib/schemas/nlqIntent";

import type { PlayerMatch } from "./resolvePlayers";
import { parseRules } from "./ruleParser";
import { readOpponents } from "./opponents";
import { readRoster } from "./rosterWords";
import { tokenize } from "./resolvePlayers";
import { readTime, type TimeScope } from "./timeWords";

/** The question without the words code reads itself (time, opponents); the question as asked when there are none. */
function modelText(question: string, scope: TimeScope, playerNamed: boolean): string {
  const tokens = tokenize(question.replace(/%/g, " percent "));
  // A roster word means the League filter only in a ranking; next to a player it stays for the model to refuse.
  const roster = playerNamed ? [] : readRoster(tokens).at;
  const read = new Set([...readTime(question, scope).used, ...readOpponents(question, playerNamed).used, ...roster]);
  return read.size === 0 ? question : tokens.filter((_, i) => !read.has(i)).join(" ");
}

/** "saved" is an answer the user corrected earlier, replayed without asking anything. */
export type AnswerPath = "rules" | "model" | "saved";

export type Interpretation =
  /** `unrecognized` (model path only): words the rules could not place, so a misread is visible. */
  { kind: "intent"; intent: QueryIntent; path: AnswerPath; unrecognized?: string[] } | { kind: "message"; text: string };

/**
 * Rules first: they are instant, free and deterministic. Only a question they cannot fully read goes
 * to the model, and if the model is unavailable the user is told why neither could answer.
 */
export async function interpretQuestion(args: {
  question: string;
  matches: readonly PlayerMatch[];
  seasons: readonly number[];
  chipGroups: readonly FilterChipGroup[];
  maxWeeks?: Readonly<Record<number, number>>;
  askModel: (question: string) => Promise<IntentOutcome>;
}): Promise<Interpretation> {
  const { question, matches, seasons, chipGroups, maxWeeks, askModel } = args;

  const rules = parseRules(question, { matches, seasons, chipGroups, maxWeeks });
  if (rules.status === "resolved") {
    return { kind: "intent", intent: rules.intent, path: "rules" };
  }
  if (rules.status === "unsupported") {
    return { kind: "message", text: rules.reason };
  }

  try {
    // Time words and opponents are read in code and put back on the answer; the model sees the rest.
    const outcome = await askModel(modelText(question, { seasons, maxWeeks }, matches.length > 0));
    return outcome.outcome === "unsupported"
      ? { kind: "message", text: outcome.reason }
      : {
          kind: "intent",
          intent: outcome.intent,
          path: "model",
          unrecognized: rules.status === "ambiguous" ? (rules.unrecognized ?? []) : [],
        };
  } catch (e) {
    const why = e instanceof Error ? e.message : String(e);
    return {
      kind: "message",
      text: `The built-in rules couldn't read this (${rules.reason}) and the model couldn't help: ${why}`,
    };
  }
}
