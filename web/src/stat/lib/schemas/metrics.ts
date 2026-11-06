import { z } from "zod";

/**
 * Mirrors `backend/schemas/metrics.py`. `metrics/metrics.json` at the repo root is the source of
 * truth for the stat definitions; both sides validate it with the same rules.
 */

const playerRoleSchema = z.enum(["passer", "rusher", "receiver"]);
const playTypeSchema = z.enum(["pass", "run", "all"]);

const MAX_ALIASES = 20;
const MAX_ALIAS_LENGTH = 60;

const aliasSchema = z
  .string()
  .max(MAX_ALIAS_LENGTH)
  .refine((a) => a !== "" && a === a.trim() && a === a.toLowerCase(), {
    message: "alias must be non-empty, trimmed and lowercase",
  })
  .refine((a) => a === a.split(/\s+/).join(" "), {
    message: "aliases use single spaces between words",
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
  label: z.string().min(1),
  category: z.string(),
  /** "league": points under the league picked in the app, so no play SQL, role or filter. */
  source: z.enum(["pbp", "league"]).default("pbp"),
  player_role: playerRoleSchema.nullish(),
  play_type: playTypeSchema.nullish(),
  base_sql: z.string().default(""),
  rate_only: z.boolean(),
  /** Which way is better, when one is ("best" and "worst" need it); unset for neutral stats like ADOT. */
  better: z.enum(["higher", "lower"]).nullish(),
  percent_format: z.boolean().default(false),
  play_filter: z.string().min(1).nullable().default(null),
  player_game_column: z.string().min(1).nullable().default(null),
  /** Only a team has this stat (it counts every play, whoever had the ball); a player query is refused. */
  team_only: z.boolean().default(false),
  /** Stats that answer one question for different roles ("EPA"); Ask picks the one that fits the subject. */
  family: z.string().min(1).nullable().default(null),
  description: z.string().nullish(),
  help: z.string().nullish(),
  aliases: z.array(aliasSchema).max(MAX_ALIASES).default([]),
  reference_values: z.array(referenceValueSchema).default([]),
});

/** Which fields a metric needs depends on its source; the backend schema says the same. */
const metricRulesSchema = metricSchema.superRefine((m, ctx) => {
  const problem = (message: string) => ctx.addIssue({ code: "custom", message });
  if (m.source === "league") {
    if (m.base_sql || m.play_filter || m.player_game_column || m.player_role || m.play_type) {
      problem(`'${m.id}' is a league metric: no play SQL, role or filter`);
    }
  } else if (!m.base_sql || !m.player_role || !m.play_type) {
    problem(`'${m.id}' needs base_sql, player_role and play_type`);
  }
});

const metricsFileSchema = z
  .object({
    schema_version: z.literal(1),
    categories: z.array(z.object({ id: z.string().min(1), label: z.string().min(1) })),
    metrics: z.array(metricRulesSchema),
  })
  .superRefine((file, ctx) => {
    const problem = (message: string) => ctx.addIssue({ code: "custom", message });

    const seenIds = new Set<string>();
    const categories = new Set<string>();
    for (const c of file.categories) {
      if (categories.has(c.id)) {
        problem(`Duplicate category id '${c.id}'`);
      }
      categories.add(c.id);
    }
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
export type MetricSource = MetricDefinitionData["source"];
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
