import type { QueryIntent } from "@/shared/lib/schemas/nlqIntent";
import type { QuerySpec } from "@/shared/lib/schemas/querySpec";

/** The model's flat intent plus the players the browser matched, as a full spec. */
export function specFromIntent(intent: QueryIntent, gsisIds: string[]): QuerySpec {
  return {
    subject: { kind: "players", gsis_ids: gsisIds },
    metrics: intent.stat_ids,
    filters: intent.filter_ids,
    granularity: intent.granularity,
    group_by: [],
    order_by: null,
    limit: null,
  };
}

/**
 * Why the engine can't run this spec yet, one message per missing capability. Empty means it can.
 * Every spec shape validates; this is the single place that says which ones execute.
 */
export function unsupportedReasons(spec: QuerySpec): string[] {
  if (spec.subject.kind !== "players") {
    // A league or team query always carries an order and limit; one message covers all of it.
    return ["League-wide leaderboards and team queries aren't supported yet."];
  }
  const reasons: string[] = [];
  if (spec.group_by.length > 0) {
    reasons.push("Splitting results by season or week isn't supported yet.");
  }
  if (spec.order_by !== null || spec.limit !== null) {
    reasons.push("Custom ordering and limits aren't supported yet.");
  }
  return reasons;
}
