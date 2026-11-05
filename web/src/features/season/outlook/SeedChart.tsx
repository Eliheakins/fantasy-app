import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis, usePlotArea, useXAxisScale } from "recharts";
import { DataTableFallback, formatPercent } from "@/viz";
import { AXIS, TICK_COLOR } from "@/viz/chartTheme";
import { BYE_SEEDS, PLAYOFF_SEEDS, seedFill } from "./logic";
import type { SeedRow } from "@/lib/outlookTypes";

const BAR_MAX_PX = 32;
const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];

/** The playoff line between seeds 6 and 7, and a "Bye" bracket over seeds 1 and 2, drawn from the axis scale. */
function Marks({ count }: { count: number }) {
  const scale = useXAxisScale();
  const area = usePlotArea();
  if (!area || !scale) return null;
  const cut = scale(String(PLAYOFF_SEEDS), { position: "end" });
  const byeStart = scale("1", { position: "start" });
  const byeEnd = scale(String(BYE_SEEDS), { position: "end" });
  const row = area.y - 40; // a label row above the tallest bar's value label; needs the chart's top margin of 60
  return (
    <g fontSize={12}>
      {count > PLAYOFF_SEEDS && typeof cut === "number" && (
        <>
          <line x1={cut} x2={cut} y1={row - 12} y2={area.y + area.height} stroke="var(--lf-ink)" strokeWidth={1.5} />
          <text x={cut - 6} y={row} textAnchor="end" fill="var(--lf-ink)" fontWeight={600}>Makes playoffs</text>
          <text x={cut + 6} y={row} textAnchor="start" fill={TICK_COLOR}>Misses</text>
        </>
      )}
      {typeof byeStart === "number" && typeof byeEnd === "number" && (
        <>
          <line x1={byeStart + 4} x2={byeEnd - 4} y1={row + 6} y2={row + 6} stroke={TICK_COLOR} />
          <text x={(byeStart + byeEnd) / 2} y={row} textAnchor="middle" fill={TICK_COLOR}>Bye</text>
        </>
      )}
    </g>
  );
}

/** Chance of each regular-season seed: playoff seeds Forest, misses light grey, every bar labelled, no value axis. */
export function SeedChart({ rows }: { rows: readonly SeedRow[] }) {
  const data = rows.map((r) => ({ seed: String(r.seed), p: r.p, fill: seedFill(r.seed) }));
  return (
    <div className="max-w-3xl">
      <div className="h-72 w-full" role="img" aria-label="Chance of each regular-season seed, bar chart; seeds 1 to 6 make the playoffs and 1 and 2 get a bye">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 60, right: 8, bottom: 0, left: 8 }} barCategoryGap="20%">
            <XAxis dataKey="seed" {...AXIS} stroke="var(--lf-ink)" label={{ value: "Seed", position: "insideBottom", offset: 0, fill: TICK_COLOR, fontSize: 12 }} height={40} />
            <YAxis hide domain={[0, "dataMax"]} />
            <Bar dataKey="p" maxBarSize={BAR_MAX_PX} radius={BAR_RADIUS} isAnimationActive={false}>
              {data.map((d) => <Cell key={d.seed} fill={d.fill} />)}
              <LabelList dataKey="p" position="top" formatter={(v: unknown) => formatPercent(typeof v === "number" ? v : null)} fill="var(--lf-ink)" fontSize={12} />
            </Bar>
            <Marks count={data.length} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <DataTableFallback
        summary="Show seed chances as a table"
        caption="Chance of each seed"
        columns={["Seed", "Chance"]}
        rows={rows.map((r) => [r.seed, formatPercent(r.p)])}
      />
    </div>
  );
}
