/**
 * Metric configuration for The Bridge. The definitions live in `metrics/metrics.json` at the repo
 * root (the source of truth, also read by the backend tests); this module validates the file once
 * at startup and exposes it in the shape the query builder uses.
 */
import rawMetrics from "../../../../metrics/metrics.json";

import {
  type MetricDefinitionData,
  type PlayerRole,
  type PlayTypeScope,
  parseMetricsFile,
} from "@/shared/lib/schemas/metrics";

export type { PlayerRole, PlayTypeScope };

/** Category ids come from the metrics file, so a new category needs no code change. */
export type StatCategory = string;

export interface StatDefinition {
  id: string;
  label: string;
  /** Short subtitle when no `help` tooltip, or extra context alongside help. */
  description?: string;
  /** Shown in a ? tooltip (hover/focus). Prefer this over duplicating `description`. */
  help?: string;
  category: StatCategory;
  playerRole: PlayerRole;
  playType: PlayTypeScope;
  /**
   * Aggregate SQL over filtered play rows. Use raw column names (no `main.`); the builder qualifies them.
   * For `rate_only: false`, if this is exactly `SUM(single_column)`, Total / Per play / Per game are derived.
   */
  base_sql: string;
  /** If true, the expression is used as-is (typically a rate); Total/Per game toggles are disabled in UI. */
  rate_only: boolean;
  /** Table header hint for percentage-style metrics. */
  percent_format?: boolean;
  /** Extra row predicate (e.g. `sack = 0`); stats with different filters run as separate queries. */
  playFilter?: string;
  /** Lowercase phrases people use for this stat; shown to the model and used for matching. */
  aliases: string[];
}

const file = parseMetricsFile(rawMetrics);

function toStat(m: MetricDefinitionData): StatDefinition {
  return {
    id: m.id,
    label: m.label,
    description: m.description ?? undefined,
    help: m.help ?? undefined,
    category: m.category,
    playerRole: m.player_role,
    playType: m.play_type,
    base_sql: m.base_sql,
    rate_only: m.rate_only,
    percent_format: m.percent_format || undefined,
    playFilter: m.play_filter ?? undefined,
    aliases: m.aliases,
  };
}

export const STAT_CATEGORY_ORDER: StatCategory[] = file.categories.map((c) => c.id);

export const STAT_CATEGORY_LABELS: Record<StatCategory, string> = Object.fromEntries(
  file.categories.map((c) => [c.id, c.label]),
);

export const STAT_DEFINITIONS: StatDefinition[] = file.metrics.map(toStat);

const STATS_BY_ID = new Map(STAT_DEFINITIONS.map((s) => [s.id, s]));

export function getStatById(id: string | null): StatDefinition | undefined {
  return id === null ? undefined : STATS_BY_ID.get(id);
}

export function getStatsByCategory(category: StatCategory): StatDefinition[] {
  return STAT_DEFINITIONS.filter((s) => s.category === category);
}

export function playerColumnForRole(
  role: PlayerRole,
): "passer_player_id" | "rusher_player_id" | "receiver_player_id" {
  switch (role) {
    case "passer":
      return "passer_player_id";
    case "rusher":
      return "rusher_player_id";
    case "receiver":
      return "receiver_player_id";
  }
}
