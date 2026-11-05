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
} from "@/stat/lib/schemas/metrics";

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
   * Aggregate SQL over filtered play rows. Use raw column names; the engine reads those columns from the Parquet shards.
   * For `rate_only: false`, if this is exactly `SUM(single_column)`, Total / Per play / Per game are derived.
   */
  base_sql: string;
  /** If true, the expression is used as-is (typically a rate); Total/Per game toggles are disabled in UI. */
  rate_only: boolean;
  /** Which way is better, when one is; "best" and "worst" mean nothing for a stat without it. */
  better?: "higher" | "lower";
  /** Table header hint for percentage-style metrics. */
  percent_format?: boolean;
  /**
   * The player-game column that holds this stat's official total. Present on counting stats only;
   * with it, a query that needs no situational filter is answered from the small tier-1 table.
   */
  playerGameColumn?: string;
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
    better: m.better ?? undefined,
    percent_format: m.percent_format || undefined,
    playFilter: m.play_filter ?? undefined,
    playerGameColumn: m.player_game_column ?? undefined,
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

export function playerColumnForRole(role: PlayerRole): "passer_player_id" | "rusher_player_id" | "receiver_player_id" {
  switch (role) {
    case "passer":
      return "passer_player_id";
    case "rusher":
      return "rusher_player_id";
    case "receiver":
      return "receiver_player_id";
  }
}
