import { getFilterChipGroups } from "@/shared/lib/filterChipGroups";
import {
  getStatById,
  playerColumnForRole,
  type StatDefinition,
} from "@/shared/config/statDictionary";
import type { GranularityMode } from "@/shared/types/queryBuilder";
import type { QueryResult } from "@/shared/types/workbench";

export function sqlQuotedInList(gsisIds: string[]): string {
  return gsisIds.map((id) => `'${id.replace(/'/g, "''")}'`).join(", ");
}

export function buildPlaysCteBody(viewNames: string[]): string {
  if (viewNames.length === 0) {
    throw new Error("No nfl_pbp views available. Pin players so shards can load.");
  }
  if (viewNames.length === 1) {
    return `SELECT * FROM ${viewNames[0]}`;
  }
  return viewNames.map((v) => `SELECT * FROM ${v}`).join("\nUNION ALL BY NAME\n");
}

/** Active games per player (any role), no situational filters — used as `sub.game_count`. */
export function buildActiveGamesCte(): string {
  return `active_games AS (
  SELECT
    pid,
    COUNT(DISTINCT game_id) AS game_count
  FROM (
    SELECT game_id, passer_player_id AS pid FROM plays WHERE passer_player_id IS NOT NULL
    UNION ALL
    SELECT game_id, rusher_player_id FROM plays WHERE rusher_player_id IS NOT NULL
    UNION ALL
    SELECT game_id, receiver_player_id FROM plays WHERE receiver_player_id IS NOT NULL
  ) AS _activity_rows
  GROUP BY pid
)`;
}

export function effectiveGranularity(
  stat: StatDefinition | undefined,
  requested: GranularityMode,
): GranularityMode {
  if (stat?.rate_only) {
    return "per_play";
  }
  return requested;
}

/** Play-row columns to prefix with `main.` inside metric SQL (longest first; excludes `game_count` on `sub`). */
const METRIC_QUALIFY_COLUMNS: string[] = [
  "yards_after_catch",
  "yards_gained",
  "pass_touchdown",
  "rush_touchdown",
  "game_seconds_remaining",
  "score_differential",
  "yardline_100",
  "number_of_pass_rushers",
  "avg_intended_air_yards",
  "avg_expected_yac",
  "avg_time_to_throw",
  "expected_run_yards",
  "incomplete_pass",
  "interception",
  "complete_pass",
  "defenders_in_box",
  "avg_separation",
  "avg_time_to_los",
  "offense_personnel",
  "passer_rating",
  "avg_cushion",
  "first_down",
  "passer_player_id",
  "rusher_player_id",
  "receiver_player_id",
  "xyac_epa",
  "qb_epa",
  "posteam_type",
  "season_type",
  "air_yards",
  "vegas_wpa",
  "touchdown",
  "qb_hit",
  "posteam",
  "defteam",
  "season",
  "success",
  "cpoe",
  "epa",
  "down",
  "week",
  "qtr",
  "wpa",
  "wind",
  "temp",
  "sack",
  "xpass",
  "efficiency",
  "is_red_zone",
  "goal_to_go",
  "ydstogo",
  "play_type",
];

export function qualifyMetricSql(expr: string): string {
  let out = expr;
  for (const col of METRIC_QUALIFY_COLUMNS) {
    const re = new RegExp(`(?<!main\\.)(?<!sub\\.)\\b${col}\\b`, "g");
    out = out.replace(re, `main.${col}`);
  }
  return out;
}

/**
 * Builds the SELECT metric expression for a stat: qualifies `base_sql`, applies granularity when
 * `rate_only` is false and `base_sql` is a plain `SUM(single_col)`.
 */
export function metricExpressionForGranularity(stat: StatDefinition, granularity: GranularityMode): string {
  const q = (sql: string) => qualifyMetricSql(sql.trim());

  if (stat.rate_only) {
    return q(stat.base_sql);
  }

  const trimmed = stat.base_sql.trim();
  const sumCol = /^SUM\((\w+)\)$/i.exec(trimmed);
  if (sumCol) {
    const col = sumCol[1];
    switch (granularity) {
      case "total":
        return q(`SUM(${col})`);
      case "per_play":
        return q(`AVG(${col})`);
      case "per_game":
        return q(`SUM(${col}) / NULLIF(MAX(sub.game_count), 0)`);
      default:
        return q(`AVG(${col})`);
    }
  }

  return q(stat.base_sql);
}

/** Safe SQL column alias for a stat id (used in multi-metric SELECT). */
export function metricSelectAlias(statId: string): string {
  return `m_${statId.replace(/[^a-zA-Z0-9_]/g, "_")}`;
}

/**
 * Bucket stats by (playerRole, playType, playFilter) while preserving global stat id order within
 * each bucket. A stat's row filter can't be applied to its neighbours, so each filter gets its own query.
 */
function buildStatGroupsInSelectOrder(statIds: string[]): StatDefinition[][] {
  const groups: StatDefinition[][] = [];
  const keyToIdx = new Map<string, number>();
  for (const id of statIds) {
    const s = getStatById(id);
    if (!s) {
      continue;
    }
    const k = `${s.playerRole}:${s.playType}:${s.playFilter ?? ""}`;
    let idx = keyToIdx.get(k);
    if (idx === undefined) {
      idx = groups.length;
      keyToIdx.set(k, idx);
      groups.push([]);
    }
    groups[idx]!.push(s);
  }
  return groups;
}

export interface StatQueryPlan {
  sql: string;
  /** Stat ids matching SELECT aliases (same order as metric columns). */
  statIdsOrdered: string[];
}

function buildSqlForStatGroup(
  stats: StatDefinition[],
  params: {
    filterChipState: Record<string, boolean>;
    gsisIds: string[];
    viewNames: string[];
    granularity: GranularityMode;
    minPlays: number;
  },
): string {
  const first = stats[0]!;
  const { filterChipState, gsisIds, viewNames, granularity, minPlays } = params;
  const playerCol = playerColumnForRole(first.playerRole);

  const metricLines = stats.map((s) => {
    const g = effectiveGranularity(s, granularity);
    const expr = metricExpressionForGranularity(s, g);
    return `  ${expr} AS ${metricSelectAlias(s.id)}`;
  });

  const cteBody = buildPlaysCteBody(viewNames);
  const whereParts: string[] = [`main.${playerCol} IN (${sqlQuotedInList(gsisIds)})`];

  if (first.playType === "pass") {
    whereParts.push("main.play_type = 'pass'");
  } else if (first.playType === "run") {
    whereParts.push("main.play_type = 'run'");
  }
  if (first.playFilter) {
    whereParts.push(`(${qualifyMetricSql(first.playFilter)})`);
  }

  const filterSql = buildFilterWhereSql(filterChipState, qualifyFilterPredicate);
  if (filterSql) {
    whereParts.push(`(${filterSql})`);
  }

  const whereClause = whereParts.join(" AND ");
  const havingClause = minPlays > 0 ? `HAVING COUNT(*) >= ${Math.floor(minPlays)}` : "";
  const activeGamesCte = buildActiveGamesCte();
  const orderAlias = metricSelectAlias(stats[0]!.id);

  return `
WITH plays AS (
${cteBody}
),
${activeGamesCte}
SELECT
  main.${playerCol} AS player_id,
${metricLines.join(",\n")}
FROM plays AS main
LEFT JOIN active_games AS sub ON sub.pid = main.${playerCol}
WHERE ${whereClause}
GROUP BY main.${playerCol}
${havingClause}
ORDER BY ${orderAlias} DESC NULLS LAST
`.trim();
}

/**
 * One SQL plan per distinct (role, play_type, play_filter) bucket. Run each plan and merge with `mergeStatQueryResults`.
 */
export function buildStatQueryPlans(params: {
  statIds: string[];
  filterChipState: Record<string, boolean>;
  gsisIds: string[];
  viewNames: string[];
  granularity: GranularityMode;
  minPlays: number;
}): StatQueryPlan[] {
  const groups = buildStatGroupsInSelectOrder(params.statIds);
  const nonEmpty = groups.filter((g) => g.length > 0);
  if (nonEmpty.length === 0) {
    throw new Error("Select at least one stat.");
  }
  return nonEmpty.map((stats) => ({
    sql: buildSqlForStatGroup(stats, params),
    statIdsOrdered: stats.map((s) => s.id),
  }));
}

/** Merge DuckDB result sets on player_id; fills missing metrics with null. Sort by first stat descending. */
export function mergeStatQueryResults(results: QueryResult[], selectedStatIds: string[]): QueryResult {
  const merged = new Map<string, Record<string, unknown>>();

  for (const res of results) {
    for (const row of res.rows) {
      const pid = String(row.player_id ?? "");
      if (!pid) {
        continue;
      }
      if (!merged.has(pid)) {
        merged.set(pid, { player_id: pid });
      }
      const acc = merged.get(pid)!;
      for (const col of res.columns) {
        if (col === "player_id") {
          continue;
        }
        acc[col] = row[col];
      }
    }
  }

  const columns = ["player_id", ...selectedStatIds.map(metricSelectAlias)];
  const rows = Array.from(merged.values()).map((row) => {
    const out: Record<string, unknown> = { player_id: row.player_id };
    for (const id of selectedStatIds) {
      const a = metricSelectAlias(id);
      out[a] = row[a] ?? null;
    }
    return out;
  });

  const firstAlias = metricSelectAlias(selectedStatIds[0]!);
  rows.sort((a, b) => {
    const va = Number(a[firstAlias]);
    const vb = Number(b[firstAlias]);
    if (Number.isNaN(va) && Number.isNaN(vb)) {
      return 0;
    }
    if (Number.isNaN(va)) {
      return 1;
    }
    if (Number.isNaN(vb)) {
      return -1;
    }
    return vb - va;
  });

  return { columns, rows };
}

/** Column names that appear in filter predicates → qualify with main. for stitched PBP. */
const FILTER_PREDICATE_COLUMNS =
  "down|ydstogo|yardline_100|qtr|game_seconds_remaining|score_differential|goal_to_go|play_type|season|week|posteam|defteam|posteam_type|season_type|passer_player_id|rusher_player_id|receiver_player_id|epa|qb_epa|success|air_yards|yards_gained|yards_after_catch|complete_pass|incomplete_pass|interception|pass_touchdown|rush_touchdown|first_down|cpoe|sack|touchdown|fumble_lost|qb_hit|xpass|xyac_epa|wpa|vegas_wpa|temp|wind|defenders_in_box|number_of_pass_rushers|offense_personnel|avg_time_to_throw|avg_intended_air_yards|passer_rating|avg_separation|avg_cushion|avg_expected_yac|avg_time_to_los|expected_run_yards|efficiency|is_red_zone";

function qualifyFilterPredicate(predicate: string): string {
  const re = new RegExp(`\\b(${FILTER_PREDICATE_COLUMNS})\\b`, "g");
  return predicate.replace(re, "main.$1");
}

export function buildFilterWhereSql(
  filterChipState: Record<string, boolean>,
  qualifyPredicate: (p: string) => string = (p) => p,
): string {
  const parts: string[] = [];

  for (const group of getFilterChipGroups()) {
    const active = group.options.filter((o) => filterChipState[o.id]);
    if (active.length === 0) {
      continue;
    }
    const inner = active
      .map((o) => `(${qualifyPredicate(o.predicate)})`)
      .join(group.combine === "or" ? " OR " : " AND ");
    parts.push(`(${inner})`);
  }

  if (parts.length === 0) {
    return "";
  }
  return parts.join(" AND ");
}

/** Single-plan SQL (convenience when only one stat is needed). */
export function buildQueryBuilderSql(params: {
  statId: string | null;
  filterChipState: Record<string, boolean>;
  gsisIds: string[];
  viewNames: string[];
  granularity: GranularityMode;
  minPlays: number;
}): string {
  const { statId, filterChipState, gsisIds, viewNames, granularity, minPlays } = params;
  if (!statId) {
    throw new Error("Select a stat.");
  }
  const plans = buildStatQueryPlans({
    statIds: [statId],
    filterChipState,
    gsisIds,
    viewNames,
    granularity,
    minPlays,
  });
  return plans[0]?.sql ?? "";
}

export function describeStat(stat: StatDefinition | undefined): string {
  if (!stat) {
    return "";
  }
  const role = stat.playerRole;
  const pt = stat.playType === "all" ? "all plays" : stat.playType;
  const sqlPreview =
    stat.base_sql.length > 72 ? `${stat.base_sql.slice(0, 72)}…` : stat.base_sql;
  let s = `${sqlPreview} · ${role} · ${pt}`;
  if (stat.rate_only) {
    s += " · rate_only";
  }
  return s;
}

export function formatMetricValueHeader(
  stat: StatDefinition | undefined,
  granularity: GranularityMode,
): string {
  if (!stat) {
    return "metric_value";
  }
  const g = effectiveGranularity(stat, granularity);
  const pct = stat.percent_format ? " %" : "";
  if (stat.rate_only) {
    return `${stat.label}${pct} (rate)`;
  }
  if (g === "total") {
    return `${stat.label}${pct} (total)`;
  }
  if (g === "per_game") {
    return `${stat.label}${pct} (per game)`;
  }
  return `${stat.label}${pct} (per play)`;
}
