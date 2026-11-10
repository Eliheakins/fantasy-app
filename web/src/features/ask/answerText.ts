import { getStatById } from "@/stat/config/statDictionary";
import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import { formatQueryValue } from "@/stat/lib/formatQueryValue";
import { formatMetricValueHeader, metricSelectAlias } from "@/stat/lib/queryBuilder";
import type { GranularityMode } from "@/stat/types/queryBuilder";
import type { QueryResult } from "@/stat/types/workbench";

export interface AnswerInput {
  result: QueryResult;
  statIds: string[];
  granularity: GranularityMode;
  filterIds: string[];
  chipGroups: FilterChipGroup[];
  nameByGsis: ReadonlyMap<string, string>;
  /** Number the lines, for a leaderboard where the order is the answer. */
  ranked?: boolean;
  /** Which column names the row: player_id, or team_id for team rows. */
  idColumn?: "player_id" | "team_id";
  /** The selected league's name, shown on league stats; null leaves the label generic. */
  leagueName?: string | null;
  /** Each player's latest N games only; a ranking's position and rookie filters. */
  lastGames?: number | null;
  position?: string | null;
  rookie?: boolean;
}

export interface Answer {
  /** What the numbers cover, e.g. "2023, Playoffs". */
  context: string;
  /** One line per player, or per player and season or week when split. */
  lines: string[];
  /** The same lines split around the name, so the name can be a link (gsisId is null for team rows). */
  parts: { before: string; name: string; after: string; gsisId: string | null }[];
  /** A ranking's one-line answer ("<name> leads with 1,036"), shown above the table in place of the numbered list; null otherwise. */
  leader: { name: string; after: string; gsisId: string | null } | null;
}

const NO_FILTERS_CONTEXT = "All loaded seasons";

/** Parts of a query that are not chips: the last N games, and who a ranking may list. */
export function scopeLabels(scope: { lastGames: number | null; position?: string | null; rookie?: boolean }): string[] {
  return [
    ...(scope.lastGames ? [scope.lastGames === 1 ? "Last game" : `Last ${scope.lastGames} games`] : []),
    ...(scope.position ? [`${scope.position}s only`] : []),
    ...(scope.rookie ? ["Rookies only"] : []),
  ];
}

/** Seasons first (they scope everything else), then the other filters in chip-group order. */
function filterLabels(filterIds: string[], chipGroups: FilterChipGroup[]): string[] {
  const wanted = new Set(filterIds);
  const seasons: string[] = [];
  const others: string[] = [];
  for (const group of chipGroups) {
    for (const option of group.options) {
      if (!wanted.has(option.id)) {
        continue;
      }
      if (group.id === "season") {
        seasons.push(option.label);
      } else {
        others.push(`${group.label}: ${option.label}`);
      }
    }
  }
  return [...seasons, ...others];
}

/** Deterministic text for the table; the model only chose the query, never the numbers. */
export function buildAnswer({
  result,
  statIds,
  granularity,
  filterIds,
  chipGroups,
  nameByGsis,
  ranked = false,
  idColumn = "player_id",
  leagueName = null,
  lastGames = null,
  position = null,
  rookie = false,
}: AnswerInput): Answer {
  const labels = [...filterLabels(filterIds, chipGroups), ...scopeLabels({ lastGames, position, rookie })];
  const parts = result.rows.map((row, rank) => {
    const pid = String(row[idColumn] ?? "");
    const name = nameByGsis.get(pid) ?? pid;
    const when = [
      row.season,
      row.week === undefined ? undefined : `week ${String(row.week)}`,
      row.posteam_type === undefined ? undefined : String(row.posteam_type),
    ].filter((v) => v !== undefined);
    const metrics = statIds.map((id) => {
      const header = formatMetricValueHeader(getStatById(id), granularity, leagueName);
      return `${header}: ${formatQueryValue(row[metricSelectAlias(id)])}`;
    });
    return {
      before: ranked ? `${rank + 1}. ` : "",
      name,
      after: `${when.length > 0 ? `, ${when.join(" ")}` : ""} — ${metrics.join(" · ")}`,
      gsisId: idColumn === "player_id" && pid ? pid : null,
    };
  });
  const lines = parts.map((p) => `${p.before}${p.name}${p.after}`);
  const top = result.rows[0];
  const first = parts[0];
  const leader =
    ranked && top !== undefined && first !== undefined && parts.length > 1
      ? {
          name: first.name,
          after: ` leads with ${statIds.map((id) => formatQueryValue(top[metricSelectAlias(id)])).join(" · ")}`,
          gsisId: first.gsisId,
        }
      : null;
  return { context: labels.length > 0 ? labels.join(", ") : NO_FILTERS_CONTEXT, lines, parts, leader };
}
