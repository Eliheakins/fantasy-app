import { CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import type { components } from "@/api/schema";
import { DataTableFallback, formatPercent } from "@/viz";
import { AXIS, GRID, MY_LINE } from "@/viz/chartTheme";

export type GameDayPoint = components["schemas"]["GameDayPoint"];
/** The current number as the line's last point, so the line and the headline agree. */
export type NowPoint = { at: string; win_prob: number };

const label = (iso: string) =>
  new Date(iso).toLocaleString("en-US", { weekday: "short", hour: "numeric", minute: "2-digit" });

/** My chance to win at each saved live tick of the week, then now: one ink line, straight segments (no values invented between updates). */
export function WinChanceLine({ history, now }: { history: readonly GameDayPoint[]; now?: NowPoint | null }) {
  const saved = history.map((p) => ({ at: label(p.run_at), win: p.win_prob }));
  const last = history[history.length - 1];
  const points = now && now.at !== last?.run_at ? [...saved, { at: `${label(now.at)} (now)`, win: now.win_prob }] : saved;
  if (points.length < 2) {
    return <p className="text-caption text-muted">The win-chance line builds as the day goes on: one point every few minutes while games are on.</p>;
  }
  const first = points[0]!.win;
  const end = points[points.length - 1]!.win;
  return (
    <div>
      <p className="text-caption text-muted">Chance to win over the day</p>
      <div
        className="h-48 w-full"
        role="img"
        aria-label={`Chance to win over the day, line chart, from ${formatPercent(first)} to ${formatPercent(end)}, ${points.length} updates`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="at" {...AXIS} minTickGap={48} />
            <YAxis domain={[0, 1]} tickFormatter={(v: number) => formatPercent(v)} {...AXIS} width={44} />
            <Line dataKey="win" type="linear" stroke={MY_LINE} strokeWidth={3} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <DataTableFallback
        summary="Show win chance per update as a table"
        columns={["Time", "Chance to win"]}
        rows={points.map((d) => [d.at, formatPercent(d.win)])}
      />
    </div>
  );
}
