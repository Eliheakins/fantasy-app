import { CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { DataTableFallback, formatPercent } from "@/viz";
import { AXIS, GRID, MY_LINE, OTHER_LINE, axisCaption } from "@/viz/chartTheme";
import { dodgeLabels, formatRunDate, type HistoryPoint, historyTeams, pivotHistory, runTicks } from "./logic";
import type { OddsHistoryRow, SeasonOddsRow } from "./types";

const END_LABEL_CHARS = 12;
const PLOT_PX = 250; // about the plot height of the h-72 chart; only used to spread labels
const LABEL_GAP_PX = 14;

type LabelProps = { x?: number; y?: number; index?: number; text: string; last: number; bold: boolean; shift: number };

/** Recharts calls this per point; only the last one gets the team name. */
function EndLabel({ x, y, index, text, last, bold, shift }: LabelProps) {
  if (index !== last || x == null || y == null) return null;
  const shown = text.length > END_LABEL_CHARS ? `${text.slice(0, END_LABEL_CHARS - 1)}…` : text;
  return (
    <text x={x + 6} y={y + shift} dy={4} fontSize={12} fontWeight={bold ? 700 : 400} fill="var(--text)">
      {shown}
    </text>
  );
}

/** Pixel offset per team so end labels of bunched lines do not overlap. */
function labelShifts(latest: HistoryPoint | undefined, teams: readonly { id: string }[]) {
  const ends = teams.flatMap((t) => {
    const v = latest?.[t.id];
    return typeof v === "number" ? [{ id: t.id, y: (1 - v) * PLOT_PX }] : [];
  });
  const placed = dodgeLabels(ends.map((e) => e.y), LABEL_GAP_PX, 0, PLOT_PX);
  return new Map(ends.map((e, i) => [e.id, (placed[i] ?? e.y) - e.y]));
}

/** Playoff odds per saved run: mine bold, rivals grey, names at the line ends. */
export function OddsHistoryChart({ odds, history }: { odds: readonly SeasonOddsRow[]; history: readonly OddsHistoryRow[] }) {
  const data = pivotHistory(history);
  const teams = historyTeams(odds, history);
  const ordered = [...teams.filter((t) => !t.isMe), ...teams.filter((t) => t.isMe)]; // mine drawn last, on top
  const last = data.length - 1;
  const shifts = labelShifts(data[last], teams);
  const ticks = runTicks(data.map((p) => p.run_at), formatRunDate);
  return (
    <div>
      <div className="h-72 w-full" role="img" aria-label="Season playoff odds for every team over saved runs, line chart; your team is the bold line">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 96, bottom: 0, left: 8 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="run_at" ticks={ticks} tickFormatter={(v: string) => formatRunDate(v)} {...AXIS} />
            <YAxis domain={[0, 1]} tickFormatter={(v: number) => formatPercent(v)} {...AXIS} width={56} label={axisCaption("Chance to make playoffs")} />
            {ordered.map((t) => (
              <Line
                key={t.id}
                dataKey={t.id}
                name={t.name}
                type="monotone"
                stroke={t.isMe ? MY_LINE : OTHER_LINE}
                strokeWidth={t.isMe ? 3 : 1}
                dot={false}
                isAnimationActive={false}
                connectNulls
                label={<EndLabel text={t.name} last={last} bold={t.isMe} shift={shifts.get(t.id) ?? 0} />}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <DataTableFallback
        summary="Show playoff odds per run as a table"
        columns={["Run", ...teams.map((t) => (t.isMe ? `${t.name} (you)` : t.name))]}
        rows={data.map((p) => [formatRunDate(p.run_at), ...teams.map((t) => formatPercent(p[t.id] as number | null))])}
      />
    </div>
  );
}
