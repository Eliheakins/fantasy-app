import { CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { DataTableFallback, formatPercent } from "@/viz";
import { historyTeams, pivotHistory } from "./logic";
import type { OddsHistoryRow, SeasonOddsRow } from "./types";

const TICK = { fill: "var(--text-muted)", fontSize: 12 };
const END_LABEL_CHARS = 12;
const shortDate = (iso: string) => iso.slice(0, 10);

type LabelProps = { x?: number; y?: number; index?: number; text: string; last: number; bold: boolean };

/** Recharts calls this per point; only the last one gets the team name. */
function EndLabel({ x, y, index, text, last, bold }: LabelProps) {
  if (index !== last || x == null || y == null) return null;
  const shown = text.length > END_LABEL_CHARS ? `${text.slice(0, END_LABEL_CHARS - 1)}…` : text;
  return (
    <text x={x + 6} y={y} dy={4} fontSize={12} fontWeight={bold ? 700 : 400} fill="var(--text)">
      {shown}
    </text>
  );
}

/** Playoff odds per saved run: mine bold, rivals grey, names at the line ends. */
export function OddsHistoryChart({ odds, history }: { odds: readonly SeasonOddsRow[]; history: readonly OddsHistoryRow[] }) {
  const data = pivotHistory(history);
  const teams = historyTeams(odds, history);
  const ordered = [...teams.filter((t) => !t.isMe), ...teams.filter((t) => t.isMe)]; // mine drawn last, on top
  const last = data.length - 1;
  return (
    <div>
      <div className="h-72 w-full" role="img" aria-label="Playoff odds over saved runs, line chart; your team is the bold line">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 96, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="run_at" tickFormatter={shortDate} tick={TICK} stroke="var(--border)" />
            <YAxis domain={[0, 1]} tickFormatter={(v: number) => formatPercent(v)} tick={TICK} stroke="var(--border)" width={40} />
            {ordered.map((t) => (
              <Line
                key={t.id}
                dataKey={t.id}
                name={t.name}
                type="monotone"
                stroke={t.isMe ? "var(--tick)" : "var(--range)"}
                strokeWidth={t.isMe ? 3 : 1}
                dot={false}
                isAnimationActive={false}
                connectNulls
                label={<EndLabel text={t.name} last={last} bold={t.isMe} />}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <DataTableFallback
        summary="Show playoff odds per run as a table"
        columns={["Run", ...teams.map((t) => (t.isMe ? `${t.name} (you)` : t.name))]}
        rows={data.map((p) => [shortDate(p.run_at), ...teams.map((t) => formatPercent(p[t.id] as number | null))])}
      />
    </div>
  );
}
