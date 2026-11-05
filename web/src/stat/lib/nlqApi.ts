import { API_BASE, joinUrl, START_API_HINT } from "@/stat/lib/config";
import { requestJson } from "@/stat/lib/http";
import { buildIntentCatalog } from "@/stat/lib/nlqCatalog";
import { type IntentOutcome, intentOutcomeSchema, type QueryIntent } from "@/stat/lib/schemas/nlqIntent";

export type { IntentOutcome, QueryIntent };

export function requestIntent(question: string, seasons: readonly number[]): Promise<IntentOutcome> {
  return requestJson(joinUrl(API_BASE, "nlq/intent"), intentOutcomeSchema, {
    what: "the Ask service",
    unreachableHint: START_API_HINT,
    init: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, ...buildIntentCatalog(seasons) }),
    },
  });
}
