import { Bar, BarChart, CartesianGrid, Customized, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { DataTableFallback, formatPercent } from "@/viz";
import { AXIS, BAR_FILL, GRID, TICK_COLOR, axisCaption } from "@/viz/chartTheme";
import type { SeedRow } from "./types";

/** Seeds 1 to 6 make the playoffs (the note under the heading says so); the cut sits between 6 and 7. */
const PLAYOFF_SEEDS = 6;

type BandScale = { (v: string): number | undefined; bandwidth: () => number };
type CutProps = { xAxisMap?: Record<string, { scale: BandScale }>; offset?: { top: number; height: number } };

/** A dashed line at seed 6.5, the edge between the last playoff bar and the first miss. */
function PlayoffCut({ xAxisMap, offset }: CutProps) {
  const scale = xAxisMap && Object.values(xAxisMap)[0]?.scale;
  const start = scale?.(String(PLAYOFF_SEEDS));
  if (!scale || start === undefined || !offset) return null;
  const x = start + scale.bandwidth();
  return (
    <g>
      <line x1={x} x2={x} y1={offset.top} y2={offset.top + offset.height} stroke={TICK_COLOR} strokeDasharray="4 3" />
      <text x={x - 4} y={offset.top + 10} textAnchor="end" fontSize={12} fill={TICK_COLOR}>Playoffs</text>
    </g>
  );
}

export function SeedChart({ rows }: { rows: readonly SeedRow[] }) {
  const data = rows.map((r) => ({ seed: String(r.seed), p: r.p }));
  return (
    <div>
      <div className="h-56 w-full" role="img" aria-label="Chance of each regular-season seed, bar chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="seed" {...AXIS} label={{ value: "Seed", position: "insideBottom", offset: -2, fill: TICK_COLOR, fontSize: 12 }} height={36} />
            <YAxis tickFormatter={(v: number) => formatPercent(v)} {...AXIS} width={56} label={axisCaption("Chance (%)")} />
            <Bar dataKey="p" fill={BAR_FILL} isAnimationActive={false} />
            {data.length > PLAYOFF_SEEDS && <Customized component={PlayoffCut} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <DataTableFallback
        summary="Show seed chances as a table"
        columns={["Seed", "Chance"]}
        rows={rows.map((r) => [r.seed, formatPercent(r.p)])}
      />
    </div>
  );
}
