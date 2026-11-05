import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import type { IntentOutcome, QueryIntent } from "@/stat/lib/schemas/nlqIntent";

import type { PlayerMatch } from "./resolvePlayers";
import { parseRules } from "./ruleParser";

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
  askModel: (question: string) => Promise<IntentOutcome>;
}): Promise<Interpretation> {
  const { question, matches, seasons, chipGroups, askModel } = args;

  const rules = parseRules(question, { matches, seasons, chipGroups });
  if (rules.status === "resolved") {
    return { kind: "intent", intent: rules.intent, path: "rules" };
  }
  if (rules.status === "unsupported") {
    return { kind: "message", text: rules.reason };
  }

  try {
    const outcome = await askModel(question);
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
