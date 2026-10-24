import { Bar, BarChart, CartesianGrid, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { DataTableFallback, formatPercent } from "@/viz";
import type { SeedRow } from "./types";

const TICK = { fill: "var(--text-muted)", fontSize: 12 };

export function SeedChart({ rows }: { rows: readonly SeedRow[] }) {
  const data = rows.map((r) => ({ seed: String(r.seed), p: r.p }));
  return (
    <div>
      <div className="h-56 w-full" role="img" aria-label="Chance of each regular-season seed, bar chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="seed" tick={TICK} stroke="var(--border)" />
            <YAxis tickFormatter={(v: number) => formatPercent(v)} tick={TICK} stroke="var(--border)" width={40} />
            <Bar dataKey="p" fill="var(--range)" isAnimationActive={false} />
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
