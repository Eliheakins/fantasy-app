import type { ReactNode } from "react";
import { Callout } from "@/components/Callout";
import { Section } from "@/components/Section";
import { currentSeason, statIdsFor } from "@/lib/statLink";
import { getStatById } from "@/stat/config/statDictionary";
import { formatQueryValue } from "@/stat/lib/formatQueryValue";
import { metricSelectAlias } from "@/stat/lib/queryBuilder";
import { formatNumber, formatPercent, RangeBar } from "@/viz";
import type { Domain } from "@/viz/rangeAxis";
import { bestIndexes, compareVerdict } from "./compare";
import type { PlayerProfile } from "./profile";
import { useSeasonTotals } from "./useSeasonTotals";

const RANGE_WIDTH = 160;
const HEAD = "px-2 py-2 text-left font-semibold";
const CELL = "px-2 py-2 tabular-nums";

type Measure = { label: string; values: (number | null)[]; show: (v: number) => string };

function ValueCells({ values, show }: { values: (number | null)[]; show: (v: number) => string }): ReactNode {
  const best = bestIndexes(values);
  return values.map((v, i) => (
    // the player order is fixed by the URL, so the index is a stable key
    <td key={i} className={`${CELL} ${best.has(i) ? "font-semibold text-focus" : ""}`}>
      {v === null ? "—" : show(v)}
      {best.has(i) && <span className="sr-only"> (best)</span>}
    </td>
  ));
}

/** Projection measures from the profiles, then the season's totals for each stat a compared position has. */
export function CompareSummary({
  ids,
  names,
  profiles,
  domain,
}: {
  ids: readonly string[];
  names: readonly string[];
  profiles: readonly PlayerProfile[];
  domain: Domain | null;
}) {
  const positions = profiles.map((p) => p.position ?? "");
  const statIds = [...new Set(positions.flatMap((p) => statIdsFor(p) ?? []))];
  const totals = useSeasonTotals(ids, statIds, currentSeason());
  const rowOf = new Map((totals.data?.rows ?? []).map((r) => [String(r.player_id), r]));
  const measures: Measure[] = [
    { label: "Median, next game", values: profiles.map((p) => p.median), show: formatNumber },
    { label: "Chance to play", values: profiles.map((p) => p.chance_to_play), show: formatPercent },
    { label: "Rest of season (points)", values: profiles.map((p) => p.ros_points), show: formatNumber },
    { label: "Over replacement", values: profiles.map((p) => p.ros_over_replacement), show: formatNumber },
  ];
  const stats: Measure[] = statIds.map((id) => ({
    label: getStatById(id)?.label ?? id,
    values: ids.map((gsisId, i) => {
      const raw = (statIdsFor(positions[i] ?? "") ?? []).includes(id) ? rowOf.get(gsisId)?.[metricSelectAlias(id)] : undefined;
      return typeof raw === "number" ? raw : null;
    }),
    show: (v) => formatQueryValue(v),
  }));
  const verdict = compareVerdict(names, profiles);
  return (
    <Section title="Side by side" level={2}>
      {verdict && <p className="mb-3 text-heading font-semibold">{verdict}</p>}
      {totals.isError && <Callout variant="warn">Season totals did not load: {totals.error.message}</Callout>}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-body">
          <thead>
            <tr className="border-b border-line text-muted">
              <th scope="col" className={HEAD}>
                <span className="sr-only">Measure</span>
              </th>
              {names.map((n, i) => (
                <th key={i} scope="col" className={HEAD}>
                  {n}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {measures.map((m) => (
              <tr key={m.label} className="border-b border-line">
                <th scope="row" className={`${HEAD} font-normal`}>
                  {m.label}
                </th>
                <ValueCells values={m.values} show={m.show} />
              </tr>
            ))}
            {domain && (
              <tr className="border-b border-line">
                <th scope="row" className={`${HEAD} font-normal`}>
                  Range, 10th to 90th
                </th>
                {profiles.map((p, i) => (
                  <td key={i} className={CELL}>
                    <RangeBar domain={domain} width={RANGE_WIDTH} p10={p.p10} p50={p.median} p90={p.p90} name={names[i]} />
                  </td>
                ))}
              </tr>
            )}
            {stats.map((m) => (
              <tr key={m.label} className="border-b border-line last:border-0">
                <th scope="row" className={`${HEAD} font-normal`}>
                  {m.label} <span className="text-caption text-muted">this season</span>
                </th>
                <ValueCells values={m.values} show={m.show} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}
