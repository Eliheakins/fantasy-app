import { API_BASE } from "@/shared/lib/api";
import { unifiedNlqResponseSchema } from "@/shared/lib/schemas/nlqUnified";

async function parseErrorDetail(res: Response): Promise<string> {
  let detail = res.statusText;
  try {
    const body = (await res.json()) as { detail?: string | unknown };
    if (typeof body.detail === "string") {
      detail = body.detail;
    } else if (body.detail != null) {
      detail = JSON.stringify(body.detail);
    }
  } catch {
    try {
      detail = await res.text();
    } catch {
      /* ignore */
    }
  }
  return detail || `HTTP ${res.status}`;
}

export type UnifiedNlqEntity = {
  display_name: string;
  bridge_id?: number | null;
  nfl_gsis_id?: string | null;
  cfb_espn_id?: string | null;
};

export type UnifiedNlqResponse = import("@/shared/lib/schemas/nlqUnified").UnifiedNlqResponseParsed;

export async function requestUnifiedNlq(
  question: string,
  entities: UnifiedNlqEntity[],
): Promise<UnifiedNlqResponse> {
  const base = API_BASE.replace(/\/$/, "");
  const res = await fetch(`${base}/nlq/unified`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, entities }),
  });
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res));
  }
  const raw: unknown = await res.json();
  const parsed = unifiedNlqResponseSchema.safeParse(raw);
  if (!parsed.success) {
    throw new Error(`NLQ unified response: invalid shape (${parsed.error.message})`);
  }
  return parsed.data;
}
