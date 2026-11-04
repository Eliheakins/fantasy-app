import { API_BASE } from "@/shared/lib/api";
import { buildIntentCatalog } from "@/shared/lib/nlqCatalog";
import {
  type IntentOutcome,
  intentOutcomeSchema,
  type QueryIntent,
} from "@/shared/lib/schemas/nlqIntent";

export type { IntentOutcome, QueryIntent };

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (body.detail != null) {
      return JSON.stringify(body.detail);
    }
  } catch {
    // Body was not JSON; fall through to the status line.
  }
  return res.statusText || `HTTP ${res.status}`;
}

export async function requestIntent(question: string): Promise<IntentOutcome> {
  const res = await fetch(`${API_BASE}/nlq/intent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, ...buildIntentCatalog() }),
  });
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res));
  }
  const parsed = intentOutcomeSchema.safeParse(await res.json());
  if (!parsed.success) {
    throw new Error(`Unexpected /nlq/intent response (${parsed.error.message})`);
  }
  return parsed.data;
}
