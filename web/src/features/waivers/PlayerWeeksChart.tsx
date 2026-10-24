import { Bar, BarChart, CartesianGrid, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { DataTableFallback, formatNumber } from "@/viz";
import type { PlayerWeekRow } from "./logic";

export function PlayerWeeksChart({ name, weeks }: { name: string; weeks: readonly PlayerWeekRow[] }) {
  const data = weeks.map((w) => ({ week: String(w.week), projection: w.projection }));
  return (
    <section aria-label={`${name}: next four weeks`} className="mt-4">
      <h3 className="text-body font-semibold">{name}: next four weeks</h3>
      {data.length === 0 ? (
        <p className="text-muted">No projections for the next weeks.</p>
      ) : (
        <>
          <div className="h-48 w-full" role="img" aria-label={`Projected points by week for ${name}`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="week" />
                <YAxis width={32} />
                <Bar dataKey="projection" fill="var(--accent)" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <DataTableFallback
            summary="Show data"
            columns={["Week", "Projection"]}
            rows={weeks.map((w) => [w.week, formatNumber(w.projection)])}
          />
        </>
      )}
    </section>
  );
}
