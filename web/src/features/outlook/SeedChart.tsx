import { Bar, BarChart, CartesianGrid, ResponsiveContainer, XAxis, YAxis, usePlotArea, useXAxisScale } from "recharts";
import { DataTableFallback, formatPercent } from "@/viz";
import { AXIS, BAR_FILL, GRID, TICK_COLOR, axisCaption } from "@/viz/chartTheme";
import type { SeedRow } from "./types";

/** Seeds 1 to 6 make the playoffs (the note under the heading says so); the cut sits between 6 and 7. */
const PLAYOFF_SEEDS = 6;

/** A dashed line at seed 6.5, the edge between the last playoff bar and the first miss. */
function PlayoffCut() {
  const scale = useXAxisScale();
  const area = usePlotArea();
  const x = scale?.(String(PLAYOFF_SEEDS), { position: "end" });
  if (!area || typeof x !== "number") return null;
  return (
    <g>
      <line x1={x} x2={x} y1={area.y} y2={area.y + area.height} stroke={TICK_COLOR} strokeDasharray="4 3" />
      <text x={x - 4} y={area.y + 10} textAnchor="end" fontSize={12} fill={TICK_COLOR}>Playoffs</text>
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
            <XAxis dataKey="seed" {...AXIS} label={{ value: "Seed", position: "insideBottom", offset: 0, fill: TICK_COLOR, fontSize: 12 }} height={48} />
            <YAxis tickFormatter={(v: number) => formatPercent(v)} {...AXIS} width={56} label={axisCaption("Chance (%)")} />
            <Bar dataKey="p" fill={BAR_FILL} isAnimationActive={false} />
            {data.length > PLAYOFF_SEEDS && <PlayoffCut />}
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
