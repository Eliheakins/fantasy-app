import { getStatById, type StatDefinition } from "@/stat/config/statDictionary";
import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import type { GranularityMode, Split } from "@/stat/types/queryBuilder";
import type { QueryResult } from "@/stat/types/workbench";

export function effectiveGranularity(stat: StatDefinition | undefined, requested: GranularityMode): GranularityMode {
  if (stat?.rate_only) {
    return "per_play";
  }
  // A weekly points total, or a total that adds stats of several roles, has no plays to divide by.
  return stat && stat.source !== "pbp" && requested === "per_play" ? "per_game" : requested;
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

/** The columns a split adds to each result row; a week split keeps the season too. */
export function splitColumns(split: Split | null | undefined): string[] {
  return split === "week" ? ["season", "week"] : split === "season" ? ["season"] : split === "location" ? ["posteam_type"] : [];
}

/** The key a play or game row is grouped under: the player, plus its season and week when split. */
export function splitKeyer(
  cols: Readonly<Record<string, ArrayLike<unknown>>>,
  split: Split | null | undefined,
): (playerId: string, row: number) => string {
  const columns = splitColumns(split).map((c) => {
    const column = cols[c];
    if (!column) {
      throw new Error(`The data has no ${c} column to split by.`);
    }
    return column;
  });
  return (playerId, row) => [playerId, ...columns.map((c) => String(c[row]))].join("|");
}

/** The split columns' values at a row, to put on the result row. */
export function splitValues(
  cols: Readonly<Record<string, ArrayLike<unknown>>>,
  split: Split | null | undefined,
  row: number,
): Record<string, unknown> {
  return Object.fromEntries(splitColumns(split).map((c) => [c, cols[c]![row]]));
}

/**
 * Merge per-group results on player_id (and season and week when split); fills missing metrics
 * with null. Sort by first stat descending.
 */
export function mergeStatQueryResults(
  results: QueryResult[],
  selectedStatIds: string[],
  split?: Split | null,
  idColumn: "player_id" | "team_id" = "player_id",
): QueryResult {
  const merged = new Map<string, Record<string, unknown>>();
  const groupColumns = splitColumns(split);

  for (const res of results) {
    for (const row of res.rows) {
      const pid = String(row[idColumn] ?? "");
      if (!pid) {
        continue;
      }
      const key = [pid, ...groupColumns.map((c) => String(row[c]))].join("|");
      if (!merged.has(key)) {
        merged.set(key, { [idColumn]: pid, ...Object.fromEntries(groupColumns.map((c) => [c, row[c]])) });
      }
      const acc = merged.get(key)!;
      for (const col of res.columns) {
        if (col === idColumn) {
          continue;
        }
        acc[col] = row[col];
      }
    }
  }

  const columns = [idColumn, ...groupColumns, ...selectedStatIds.map(metricSelectAlias)];
  const rows = Array.from(merged.values()).map((row) => {
    const out: Record<string, unknown> = { [idColumn]: row[idColumn] };
    for (const c of groupColumns) {
      out[c] = row[c];
    }
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
    // A split reads in time order: season, then week, then the first stat within each.
    for (const c of groupColumns) {
      const [x, y] = [a[c], b[c]];
      const byTime = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      if (byTime !== 0) {
        return byTime;
      }
    }
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
  options: { groups: FilterChipGroup[]; groupIds?: readonly string[] },
): string {
  const groups = options.groups;
  const parts: string[] = [];

  for (const group of groups) {
    if (options.groupIds && !options.groupIds.includes(group.id)) {
      continue;
    }
    const active = group.options.filter((o) => filterChipState[o.id]);
    if (active.length === 0) {
      continue;
    }
    const inner = active.map((o) => `(${o.predicate})`).join(group.combine === "or" ? " OR " : " AND ");
    parts.push(`(${inner})`);
  }

  return parts.join(" AND ");
}

/** What a query counts, in plain terms, for the "Query details" panel. */
export function describeQuery(params: {
  statIds: string[];
  granularity: GranularityMode;
  filterChipState: Record<string, boolean>;
  chipGroups: FilterChipGroup[];
  minPlays: number;
  lastGames?: number | null;
  position?: string | null;
  rookie?: boolean;
}): string {
  const lines = params.statIds.flatMap((id) => {
    const stat = getStatById(id);
    if (!stat) {
      return [];
    }
    if (stat.source === "league") {
      return [`${stat.label} (${effectiveGranularity(stat, params.granularity)}): the selected league's weekly points`];
    }
    if (stat.source === "derived") {
      return [`${stat.label} (${effectiveGranularity(stat, params.granularity)}): ${stat.formula ?? ""}`];
    }
    const rows = [
      `${stat.playerRole} ${stat.playType === "all" ? "plays" : `${stat.playType} plays`}`,
      stat.playFilter ? `only where ${stat.playFilter}` : null,
    ].filter(Boolean);
    return [`${stat.label} (${effectiveGranularity(stat, params.granularity)}): ${stat.base_sql}\n    over ${rows.join(", ")}`];
  });
  const where = buildFilterWhereSql(params.filterChipState, { groups: params.chipGroups });
  lines.push(where ? `Filters: ${where}` : "Filters: none");
  if (params.minPlays > 0) {
    lines.push(`Minimum rows per player: ${Math.floor(params.minPlays)}`);
  }
  if (params.lastGames) {
    lines.push(`Only each player's latest ${params.lastGames} game(s) within those filters`);
  }
  if (params.position || params.rookie) {
    lines.push(`Only ${[params.rookie ? "rookies" : null, params.position ? `${params.position}s` : null].filter(Boolean).join(", ")}`);
  }
  return lines.join("\n");
}

/** A stat's label; a league stat names the selected league, which only the UI knows (the catalog stays generic). */
export function statLabel(stat: StatDefinition, leagueName?: string | null): string {
  return stat.source === "league" && leagueName ? `${stat.label} (${leagueName})` : stat.label;
}

export function formatMetricValueHeader(
  stat: StatDefinition | undefined,
  granularity: GranularityMode,
  leagueName?: string | null,
): string {
  if (!stat) {
    return "metric_value";
  }
  const label = statLabel(stat, leagueName);
  const g = effectiveGranularity(stat, granularity);
  const pct = stat.percent_format ? " %" : "";
  if (stat.rate_only) {
    return `${label}${pct} (rate)`;
  }
  if (g === "total") {
    return `${label}${pct} (total)`;
  }
  if (g === "per_game") {
    return `${label}${pct} (per game)`;
  }
  return `${label}${pct} (per play)`;
}
