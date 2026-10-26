import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { Delta, NOISE_PERCENT, NOISE_POINTS, NOISE_WINS, formatNumber, formatPercent } from "@/viz";
import { barSpan, maxAbsDiff, oddsComparison, resultSentence, toPoints } from "./logic";
import type { LastWeekRow, OddsChangeRow, ProjectionMissRow } from "./types";

const BAR_HALF = 60;
const BAR_HEIGHT = 10;
const UNKNOWN = "not available";

function Figure({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-caption text-muted">{label}</dt>
      <dd className="tabular-nums">{children}</dd>
    </div>
  );
}

/** Last week's game: result sentence, then the three figures the League page totals over the season. */
export function LastWeek({ row, currentWeek }: { row: LastWeekRow | null; currentWeek: number | null }) {
  if (row === null) {
    return (
      <p className="text-body text-muted">
        {currentWeek !== null && currentWeek <= 1
          ? "Week 1: there is no earlier week yet."
          : "Last week's game has no final score yet."}
      </p>
    );
  }
  return (
    <div className="card-flat">
      <p className="text-body font-semibold">Week {row.week}: {resultSentence(row)}</p>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3">
        <Figure label="Bench points left (best lineup minus started)">
          {row.bench_points_left === null ? UNKNOWN : formatNumber(row.bench_points_left)}
        </Figure>
        <Figure label="Luck (wins, that week)">
          {row.luck === null ? UNKNOWN : <Delta points={row.luck} noise={NOISE_WINS} />}
        </Figure>
      </dl>
    </div>
  );
}

function DiffBar({ diff, max }: { diff: number | null; max: number }) {
  const span = barSpan(diff, max, BAR_HALF);
  return (
    <svg aria-hidden width={BAR_HALF * 2} height={BAR_HEIGHT} className="max-w-full shrink-0">
      <rect width={BAR_HALF * 2} height={BAR_HEIGHT} rx={2} className="fill-border" opacity={0.4} />
      {span && <rect x={span.x} width={span.width} height={BAR_HEIGHT} rx={2} className="fill-range" />}
      <line x1={BAR_HALF} x2={BAR_HALF} y1={0} y2={BAR_HEIGHT} className="stroke-text" strokeWidth={1.5} />
    </svg>
  );
}

function columns(max: number): Column<ProjectionMissRow>[] {
  return [
    {
      label: "Player",
      role: "primary",
      render: (r) => (
        <>
          {r.full_name ?? r.gsis_id} <span className="text-caption font-normal text-muted">{r.position}</span>
        </>
      ),
    },
    { label: "Points", numeric: true, render: (r) => formatNumber(r.points) },
    { label: "Projection", numeric: true, render: (r) => (r.projection === null ? "no projection" : formatNumber(r.projection)) },
    {
      label: "Points minus projection",
      numeric: true,
      render: (r) => (r.diff === null ? "–" : <Delta points={r.diff} noise={NOISE_POINTS} />),
    },
    {
      label: "Bar (left under, right over)",
      render: (r) => <DiffBar diff={r.diff} max={max} />,
    },
  ];
}

/** Starters against their saved projection. The bar sits beside the signed number; it never carries the meaning alone. */
export function Performance({ rows }: { rows: readonly ProjectionMissRow[] }) {
  if (rows.length === 0) return <p className="text-body text-muted">No starters were scored last week.</p>;
  const compared = rows.some((r) => r.diff !== null);
  const shown = compared ? columns(maxAbsDiff(rows)) : columns(0).slice(0, 2); // player and points only
  return (
    <>
      {!compared && (
        <p className="mb-2 text-body text-muted">
          No saved projections for this week, so there is nothing to compare. Projections were first saved in week 7.
        </p>
      )}
      <ResponsiveTable
        caption="Starters: points against projection"
        columns={shown}
        rows={rows}
        rowKey={(r) => r.gsis_id}
      />
    </>
  );
}

const NO_EARLIER = "no earlier run";

function Change({ fraction }: { fraction: number | null }) {
  const pp = toPoints(fraction);
  return pp === null ? <span className="text-muted">{NO_EARLIER}</span> : <Delta points={pp} noise={NOISE_PERCENT} />;
}

const ODDS_COLUMNS: Column<OddsChangeRow>[] = [
  { label: "Team", role: "primary", render: (r) => (r.is_me ? `${r.team_name} (you)` : r.team_name) },
  { label: "Playoff odds", numeric: true, render: (r) => formatPercent(r.p_playoffs) },
  { label: "Change (% pts)", numeric: true, render: (r) => <Change fraction={r.d_playoffs} /> },
  { label: "Title odds", numeric: true, render: (r) => formatPercent(r.p_title) },
  { label: "Change (% pts)", numeric: true, render: (r) => <Change fraction={r.d_title} /> },
];

export function OddsChange({ rows, mineLabel }: { rows: readonly OddsChangeRow[]; mineLabel: boolean }) {
  const cmp = oddsComparison(rows);
  if (cmp === null) return <p className="text-body text-muted">No simulation runs saved yet. Run <code>make refresh</code>.</p>;
  return (
    <>
      <p className="mb-2 text-caption text-muted">
        {cmp.previous === null
          ? `Latest run is for week ${cmp.latest}; there is no earlier week's run to compare with yet.`
          : `Latest run (week ${cmp.latest}) against the last run of week ${cmp.previous}.`}
      </p>
      <ResponsiveTable
        caption="Season odds and change since the earlier run"
        columns={mineLabel ? ODDS_COLUMNS : ODDS_COLUMNS.map((c, i) => (i === 0 ? { ...c, render: (r: OddsChangeRow) => r.team_name } : c))}
        rows={rows}
        rowKey={(r) => String(r.roster_id)}
        isStrong={(r) => r.is_me}
      />
    </>
  );
}
