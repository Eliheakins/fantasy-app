import { CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { DataTableFallback, formatPercent } from "@/viz";
import { useMinWidth } from "@/hooks/useMediaQuery";
import { AXIS, GRID, MY_LINE, OTHER_LINE, axisCaption } from "@/viz/chartTheme";
import { dodgeLabels, formatRunDate, type HistoryPoint, historyTeams, pivotHistory, runTicks } from "./logic";
import type { OddsHistoryRow, SeasonOddsRow } from "./types";

const END_LABEL_CHARS = 12;
const PLOT_PX = 250; // about the plot height of the h-72 chart; only used to spread labels
const LABEL_GAP_PX = 14;
const PHONE_LABEL_CHARS = 9;

type LabelProps = { x?: number; y?: number; index?: number; text: string; last: number; bold: boolean; shift: number; maxChars: number };

/** Recharts calls this per point; only the last one gets the team name. */
function EndLabel({ x, y, index, text, last, bold, shift, maxChars }: LabelProps) {
  if (index !== last || x == null || y == null) return null;
  const shown = text.length > maxChars ? `${text.slice(0, maxChars - 1)}…` : text;
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

/** Ids that get a name at the line end: my team, plus the highest and lowest on desktop. */
function labeledIds(latest: HistoryPoint | undefined, teams: readonly { id: string; isMe: boolean }[], extremes: boolean): Set<string> {
  const ids = new Set(teams.filter((t) => t.isMe).map((t) => t.id));
  if (!extremes) return ids;
  const known = teams.flatMap((t) => (typeof latest?.[t.id] === "number" ? [{ id: t.id, v: latest[t.id] as number }] : []));
  const sorted = [...known].sort((a, b) => b.v - a.v);
  for (const t of [sorted[0], sorted[sorted.length - 1]]) if (t) ids.add(t.id);
  return ids;
}

/** Playoff odds per saved run: mine bold, rivals grey, names at the line ends. */
export function OddsHistoryChart({ odds, history }: { odds: readonly SeasonOddsRow[]; history: readonly OddsHistoryRow[] }) {
  const data = pivotHistory(history);
  const teams = historyTeams(odds, history);
  const ordered = [...teams.filter((t) => !t.isMe), ...teams.filter((t) => t.isMe)]; // mine drawn last, on top
  const last = data.length - 1;
  const wide = useMinWidth("lg");
  const named = labeledIds(data[last], teams, wide);
  const shifts = labelShifts(data[last], teams.filter((t) => named.has(t.id)));
  const ticks = runTicks(data.map((p) => p.run_at), formatRunDate);
  return (
    <div>
      <div className="h-72 w-full" role="img" aria-label="Season playoff odds for every team over saved runs, line chart; the bold line is the team being viewed">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: wide ? 96 : 64, bottom: 0, left: 8 }}>
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
                label={named.has(t.id) ? <EndLabel text={t.name} last={last} bold={t.isMe} shift={shifts.get(t.id) ?? 0} maxChars={wide ? END_LABEL_CHARS : PHONE_LABEL_CHARS} /> : undefined}
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
