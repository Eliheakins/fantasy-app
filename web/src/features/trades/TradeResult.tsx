import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { DataTableFallback, Dumbbell } from "@/viz";
import { formatSigned, formatValue, sideMeasures } from "./logic";
import { Notice } from "./Notice";
import type { TradeEvaluation, TradeSide } from "./types";

type RosterChange = TradeEvaluation["roster_changes"][number];
const CHANGE_COLUMNS: readonly Column<RosterChange>[] = [
  { label: "Team", render: (c) => c.team_name },
  { label: "Action", render: (c) => c.action },
  { label: "Player", render: (c) => c.full_name },
  { label: "Position", render: (c) => c.position },
];

const MIN_HALF_SPAN = { percent: 2, wins: 0.25 } as const;

/** Same scale for both teams (so changes compare), centred on this team's own before/after. */
function domainFor(index: 0 | 1 | 2, side: TradeSide, sides: readonly TradeSide[]): readonly [number, number] {
  const measure = sideMeasures(side)[index];
  const floor = measure.percent ? MIN_HALF_SPAN.percent : MIN_HALF_SPAN.wins;
  const half = Math.max(floor, ...sides.map((s) => Math.abs(sideMeasures(s)[index].after - sideMeasures(s)[index].before) * 1.5));
  const centre = (measure.before + measure.after) / 2;
  return [centre - half, centre + half];
}

function SideCard({ title, side, sides }: { title: string; side: TradeSide; sides: readonly TradeSide[] }) {
  const measures = sideMeasures(side);
  return (
    <section aria-label={title} className="rounded border border-border bg-surface p-3">
      <h3 className="mb-2 font-semibold">{title}</h3>
      <dl className="space-y-2">
        {measures.map((m, i) => (
          <div key={m.key} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
            <dt className="text-muted">{m.label}</dt>
            <dd className="flex items-center gap-3">
              <span className="w-14 text-right font-semibold tabular-nums">{formatValue(m.after, m.percent)}</span>
              <span className="inline-block w-44">
              <Dumbbell
                before={m.before}
                after={m.after}
                domain={domainFor(i as 0 | 1 | 2, side, sides)}
                measure={m.label}
                percent={m.percent}
                width={110}
              />
              </span>
            </dd>
          </div>
        ))}
      </dl>
      <DataTableFallback
        summary="Show the numbers"
        columns={["Measure", "Before", "After", "Change"]}
        rows={measures.map((m) => [
          m.label,
          formatValue(m.before, m.percent),
          formatValue(m.after, m.percent),
          formatSigned(m.after - m.before, m.percent),
        ])}
      />
    </section>
  );
}

/** Both sides' before/after odds, the roster-moves warning and the deadline note. */
export function TradeResult({ result }: { result: TradeEvaluation }) {
  const me = result.odds.find((s) => s.side === "me");
  const them = result.odds.find((s) => s.side === "them");
  if (!me || !them) return <Notice>The response had no odds for one side of the trade.</Notice>;
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <SideCard title="Me" side={me} sides={[me, them]} />
        <SideCard title={them.team_name} side={them} sides={[me, them]} />
      </div>
      {result.warning && (
        <div>
          <Notice>{result.warning}</Notice>
          <ResponsiveTable
            caption="Automatic roster moves"
            columns={CHANGE_COLUMNS}
            rows={result.roster_changes}
            rowKey={(c) => `${c.team_name}|${c.action}|${c.full_name}`}
          />
        </div>
      )}
      {result.trade_deadline !== null && (
        <p className="text-caption text-muted">Trade deadline: week {result.trade_deadline}.</p>
      )}
    </div>
  );
}
