import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import type { IntentOutcome, QueryIntent } from "@/stat/lib/schemas/nlqIntent";

import type { PlayerMatch } from "./resolvePlayers";
import { parseRules } from "./ruleParser";
import { readTime } from "./timeWords";

/** "saved" is an answer the user corrected earlier, replayed without asking anything. */
export type AnswerPath = "rules" | "model" | "saved";

export type Interpretation =
  /** `unrecognized` (model path only): words the rules could not place, so a misread is visible. */
  | { kind: "intent"; intent: QueryIntent; path: AnswerPath; unrecognized?: string[] }
  | { kind: "message"; text: string };

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
    // Time words are read in code and put back on the answer (`withTime`); the model sees the rest.
    const outcome = await askModel(readTime(question, { seasons, maxWeeks }).rest);
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
