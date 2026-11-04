import { getStatById } from "@/shared/config/statDictionary";
import { getFilterChipGroups } from "@/shared/lib/filterChipGroups";
import { formatQueryValue } from "@/shared/lib/formatQueryValue";
import { formatMetricValueHeader, metricSelectAlias } from "@/shared/lib/queryBuilderSql";
import type { GranularityMode } from "@/shared/types/queryBuilder";
import type { QueryResult } from "@/shared/types/workbench";

export interface AnswerInput {
  result: QueryResult;
  statIds: string[];
  granularity: GranularityMode;
  filterIds: string[];
  nameByGsis: ReadonlyMap<string, string>;
}

export interface Answer {
  /** What the numbers cover, e.g. "2023, Playoffs". */
  context: string;
  /** One line per player. */
  lines: string[];
}

const NO_FILTERS_CONTEXT = "All loaded seasons";

/** Seasons first (they scope everything else), then the other filters in chip-group order. */
function filterLabels(filterIds: string[]): string[] {
  const wanted = new Set(filterIds);
  const seasons: string[] = [];
  const others: string[] = [];
  for (const group of getFilterChipGroups()) {
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
  nameByGsis,
}: AnswerInput): Answer {
  const labels = filterLabels(filterIds);
  const lines = result.rows.map((row) => {
    const pid = String(row.player_id ?? "");
    const name = nameByGsis.get(pid) ?? pid;
    const metrics = statIds.map((id) => {
      const header = formatMetricValueHeader(getStatById(id), granularity);
      return `${header}: ${formatQueryValue(row[metricSelectAlias(id)])}`;
    });
    return `${name} — ${metrics.join(" · ")}`;
  });
  return { context: labels.length > 0 ? labels.join(", ") : NO_FILTERS_CONTEXT, lines };
}
