import { z } from "zod";

/**
 * Mirrors `backend/schemas/metrics.py`. `metrics/metrics.json` at the repo root is the source of
 * truth for the stat definitions; both sides validate it with the same rules.
 */

const playerRoleSchema = z.enum(["passer", "rusher", "receiver"]);
const playTypeSchema = z.enum(["pass", "run", "all"]);

const aliasSchema = z
  .string()
  .refine((a) => a !== "" && a === a.trim() && a === a.toLowerCase(), {
    message: "alias must be non-empty, trimmed and lowercase",
  });

const referenceValueSchema = z.object({
  gsis_id: z.string(),
  player: z.string(),
  season: z.number().int(),
  season_type: z.enum(["REG", "POST"]),
  value: z.number(),
  tolerance: z.number().min(0).max(1).default(0),
  source: z.string(),
});

const metricSchema = z.object({
  id: z.string().regex(/^[a-z][a-z0-9_]*$/),
  label: z.string(),
  category: z.string(),
  player_role: playerRoleSchema,
  play_type: playTypeSchema,
  base_sql: z.string(),
  rate_only: z.boolean(),
  percent_format: z.boolean().default(false),
  play_filter: z.string().nullable().default(null),
  description: z.string().nullish(),
  help: z.string().nullish(),
  aliases: z.array(aliasSchema).default([]),
  reference_values: z.array(referenceValueSchema).default([]),
});

const metricsFileSchema = z
  .object({
    schema_version: z.literal(1),
    categories: z.array(z.object({ id: z.string(), label: z.string() })),
    metrics: z.array(metricSchema),
  })
  .superRefine((file, ctx) => {
    const problem = (message: string) => ctx.addIssue({ code: "custom", message });

    const seenIds = new Set<string>();
    const categories = new Set(file.categories.map((c) => c.id));
    const aliasOwner = new Map<string, string>();

    for (const m of file.metrics) {
      if (seenIds.has(m.id)) {
        problem(`Duplicate metric id '${m.id}'`);
      }
      seenIds.add(m.id);

      if (!categories.has(m.category)) {
        problem(`Metric '${m.id}' has an undefined category '${m.category}'`);
      }

      const own = new Set<string>();
      for (const alias of m.aliases) {
        if (own.has(alias)) {
          problem(`alias '${alias}' repeats within metric '${m.id}'`);
        }
        own.add(alias);
        const owner = aliasOwner.get(alias);
        if (owner !== undefined && owner !== m.id) {
          problem(`alias '${alias}' is used by both '${owner}' and '${m.id}'`);
        }
        aliasOwner.set(alias, m.id);
      }
    }
  });

export type MetricDefinitionData = z.infer<typeof metricSchema>;
export type MetricsFile = z.infer<typeof metricsFileSchema>;
export type PlayerRole = z.infer<typeof playerRoleSchema>;
export type PlayTypeScope = z.infer<typeof playTypeSchema>;

/** Validate the file's contents; a bad edit fails loudly, naming what is wrong. */
export function parseMetricsFile(raw: unknown): MetricsFile {
  const parsed = metricsFileSchema.safeParse(raw);
  if (!parsed.success) {
    const detail = parsed.error.issues
      .slice(0, 5)
      .map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`)
      .join("; ");
    throw new Error(`metrics.json is invalid: ${detail}`);
  }
  return parsed.data;
}
