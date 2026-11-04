import { getStatById, type StatDefinition } from "@/shared/config/statDictionary";
import type { FilterChipGroup } from "@/shared/config/queryBuilderOptions";
import { getFilterChipGroups } from "@/shared/lib/filterChipGroups";
import type { GranularityMode } from "@/shared/types/queryBuilder";
import type { QueryResult } from "@/shared/types/workbench";

export function effectiveGranularity(
  stat: StatDefinition | undefined,
  requested: GranularityMode,
): GranularityMode {
  if (stat?.rate_only) {
    return "per_play";
  }
  return requested;
}

/** Safe column alias for a stat id in a result row. */
export function metricSelectAlias(statId: string): string {
  return `m_${statId.replace(/[^a-zA-Z0-9_]/g, "_")}`;
}

/**
 * Bucket stats by (playerRole, playType, playFilter) while preserving stat id order within each
 * bucket. A stat's row filter can't be applied to its neighbours, so each filter gets its own pass.
 */
export function groupStatsByRows(statIds: string[]): StatDefinition[][] {
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

/** Merge per-group results on player_id; fills missing metrics with null. Sort by first stat descending. */
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
  // Number(null) is 0, so a missing value must be caught before converting or it outranks negatives.
  const rankOf = (row: Record<string, unknown>): number | null => {
    const raw = row[firstAlias];
    const n = raw === null || raw === undefined ? Number.NaN : Number(raw);
    return Number.isNaN(n) ? null : n;
  };
  rows.sort((a, b) => {
    const va = rankOf(a);
    const vb = rankOf(b);
    if (va === null || vb === null) {
      return va === vb ? 0 : va === null ? 1 : -1;
    }
    return vb - va;
  });

  return { columns, rows };
}

/**
 * The active filter chips as one predicate over unqualified column names, or "" when none is on.
 * Chips in a group combine per the group (usually OR); groups combine with AND. `groupIds`
 * limits it to some groups (used for the game scope of per-game stats).
 */
export function buildFilterWhereSql(
  filterChipState: Record<string, boolean>,
  options: { groups?: FilterChipGroup[]; groupIds?: readonly string[] } = {},
): string {
  const groups = options.groups ?? getFilterChipGroups();
  const parts: string[] = [];

  for (const group of groups) {
    if (options.groupIds && !options.groupIds.includes(group.id)) {
      continue;
    }
    const active = group.options.filter((o) => filterChipState[o.id]);
    if (active.length === 0) {
      continue;
    }
    const inner = active
      .map((o) => `(${o.predicate})`)
      .join(group.combine === "or" ? " OR " : " AND ");
    parts.push(`(${inner})`);
  }

  return parts.join(" AND ");
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

/** What a query counts, in plain terms, for the "Query details" panel. */
export function describeQuery(params: {
  statIds: string[];
  granularity: GranularityMode;
  filterChipState: Record<string, boolean>;
  minPlays: number;
}): string {
  const lines = params.statIds.flatMap((id) => {
    const stat = getStatById(id);
    if (!stat) {
      return [];
    }
    const rows = [
      `${stat.playerRole} ${stat.playType === "all" ? "plays" : `${stat.playType} plays`}`,
      stat.playFilter ? `only where ${stat.playFilter}` : null,
    ].filter(Boolean);
    return [`${stat.label} (${effectiveGranularity(stat, params.granularity)}): ${stat.base_sql}\n    over ${rows.join(", ")}`];
  });
  const where = buildFilterWhereSql(params.filterChipState);
  lines.push(where ? `Filters: ${where}` : "Filters: none");
  if (params.minPlays > 0) {
    lines.push(`Minimum rows per player: ${Math.floor(params.minPlays)}`);
  }
  return lines.join("\n");
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
