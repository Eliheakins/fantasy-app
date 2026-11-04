import { z } from "zod";

/**
 * The typed query the app executes, whatever produced it (the model, a rules parser, a saved URL).
 * Mirrors `backend/schemas/query_spec.py`; keep the two sets of rules identical.
 */

export const MAX_SPEC_METRICS = 5;
export const MAX_SPEC_LIMIT = 100;

const subjectSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("players"), gsis_ids: z.array(z.string()).min(1) }),
  z.object({ kind: z.literal("teams"), teams: z.array(z.string()).min(1) }),
  z.object({ kind: z.literal("league") }),
]);

const orderBySchema = z.object({
  metric: z.string(),
  direction: z.enum(["asc", "desc"]).default("desc"),
});

const querySpecSchema = z
  .object({
    subject: subjectSchema,
    metrics: z.array(z.string()).min(1).max(MAX_SPEC_METRICS),
    filters: z.array(z.string()).default([]),
    granularity: z.enum(["total", "per_game", "per_play"]).default("total"),
    group_by: z.array(z.enum(["season", "week"])).default([]),
    order_by: orderBySchema.nullable().default(null),
    limit: z.number().int().min(1).max(MAX_SPEC_LIMIT).nullable().default(null),
  })
  .superRefine((spec, ctx) => {
    const problem = (message: string) => ctx.addIssue({ code: "custom", message });

    if (new Set(spec.metrics).size !== spec.metrics.length) {
      problem("metrics repeat");
    }
    if (spec.order_by && !spec.metrics.includes(spec.order_by.metric)) {
      problem("order_by must name one of the metrics");
    }
    if (spec.subject.kind === "league" && (spec.order_by === null || spec.limit === null)) {
      problem("a league query needs order_by and limit");
    }
  });

export type QuerySpec = z.infer<typeof querySpecSchema>;

export function parseQuerySpec(raw: unknown): QuerySpec {
  const parsed = querySpecSchema.safeParse(raw);
  if (!parsed.success) {
    const detail = parsed.error.issues
      .slice(0, 5)
      .map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`)
      .join("; ");
    throw new Error(`Invalid query spec: ${detail}`);
  }
  return parsed.data;
}
