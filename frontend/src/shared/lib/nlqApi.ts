import { API_BASE, joinUrl, START_API_HINT } from "@/shared/lib/config";
import { requestJson } from "@/shared/lib/http";
import { buildIntentCatalog } from "@/shared/lib/nlqCatalog";
import { type IntentOutcome, intentOutcomeSchema, type QueryIntent } from "@/shared/lib/schemas/nlqIntent";

export type { IntentOutcome, QueryIntent };

export function requestIntent(question: string): Promise<IntentOutcome> {
  return requestJson(joinUrl(API_BASE, "nlq/intent"), intentOutcomeSchema, {
    what: "the Ask service",
    unreachableHint: START_API_HINT,
    init: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, ...buildIntentCatalog() }),
    },
  });
}
