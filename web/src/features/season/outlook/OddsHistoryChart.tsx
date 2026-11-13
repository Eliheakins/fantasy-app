import { CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DataTableFallback, formatPercent } from "@/viz";
import { useMinWidth } from "@/hooks/useMediaQuery";
import { AXIS, GRID, MY_LINE, OTHER_LINE, TICK_COLOR, axisCaption } from "@/viz/chartTheme";
import { dodgeLabels, historyTeams, type WeekPoint, weeklyHistory } from "./logic";
import type { OddsHistoryRow, SeasonOddsRow } from "@/lib/outlookTypes";

const END_LABEL_CHARS = 14;
const PHONE_LABEL_CHARS = 9;
const PLOT_PX = 250; // about the plot height of the h-72 chart; only used to spread labels
const LABEL_GAP_PX = 16;
const Y_TICKS = [0, 0.25, 0.5, 0.75, 1];

type Team = { id: string; name: string; isMe: boolean };
/** Events per week for the dots on my line: a short dot label ("Trade") and the full text for the tooltip. */
export type WeekMarks = ReadonlyMap<number, readonly { short: string; full: string }[]>;

const weekLabel = (w: number | string) => `Wk ${w}`;
const clip = (text: string, max: number) => (text.length > max ? `${text.slice(0, max - 1)}…` : text);
const valueAt = (p: WeekPoint | undefined, id: string) => (typeof p?.[id] === "number" ? (p[id] as number) : null);

type LabelProps = { x?: number; y?: number; index?: number; text: string; last: number; mine: boolean; shift: number };

/** Recharts calls this per point; only the last one gets the name and value. */
function EndLabel({ x, y, index, text, last, mine, shift }: LabelProps) {
  if (index !== last || x == null || y == null) return null;
  return (
    <text x={x + 8} y={y + shift} dy={4} fontSize={12} fontWeight={mine ? 700 : 400} fill={mine ? "var(--lf-ink)" : TICK_COLOR}>
      {text}
    </text>
  );
}

/** Mine always; on desktop also the current leader when that is someone else. */
function labeledTeams(latest: WeekPoint | undefined, teams: readonly Team[], withLeader: boolean): Team[] {
  const mine = teams.filter((t) => t.isMe);
  if (!withLeader) return mine;
  const leader = [...teams].sort((a, b) => (valueAt(latest, b.id) ?? -1) - (valueAt(latest, a.id) ?? -1))[0];
  return leader && !leader.isMe ? [...mine, leader] : mine;
}

function labelShifts(latest: WeekPoint | undefined, teams: readonly Team[]): Map<string, number> {
  const ends = teams.flatMap((t) => {
    const v = valueAt(latest, t.id);
    return v === null ? [] : [{ id: t.id, y: (1 - v) * PLOT_PX }];
  });
  const placed = dodgeLabels(
    ends.map((e) => e.y),
    LABEL_GAP_PX,
    0,
    PLOT_PX,
  );
  return new Map(ends.map((e, i) => [e.id, (placed[i] ?? e.y) - e.y]));
}

function WeekTooltip({
  active,
  label,
  data,
  teams,
  marks,
}: {
  active?: boolean;
  label?: number | string;
  data: readonly WeekPoint[];
  teams: readonly Team[];
  marks?: WeekMarks;
}) {
  const point = data.find((p) => p.week === Number(label));
  if (!active || !point) return null;
  const ranked = [...teams].sort((a, b) => (valueAt(point, b.id) ?? -1) - (valueAt(point, a.id) ?? -1));
  return (
    <div className="rounded-lg border border-line bg-surface p-3 text-caption shadow-md">
      <p className="font-semibold text-ink">Week {point.week}</p>
      {marks?.get(point.week)?.map((m) => (
        <p key={m.full} className="text-label">
          {m.full}
        </p>
      ))}
      <ul className="mt-1 space-y-0.5">
        {ranked.map((t) => (
          <li key={t.id} className="flex items-center gap-2">
            <span aria-hidden className="inline-block h-0.5 w-3" style={{ background: t.isMe ? MY_LINE : OTHER_LINE }} />
            <span className={`w-10 text-right tabular-nums ${t.isMe ? "font-semibold text-ink" : "text-ink"}`}>
              {formatPercent(valueAt(point, t.id))}
            </span>
            <span className={t.isMe ? "font-semibold text-ink" : "text-muted"}>{t.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Playoff odds by week (the last saved run of each week): mine Forest and labelled, every other team thin light grey. */
export function OddsHistoryChart({
  odds,
  history,
  marks,
  describedBy,
  titleFromWeek = null,
}: {
  odds: readonly SeasonOddsRow[];
  history: readonly OddsHistoryRow[];
  marks?: WeekMarks;
  describedBy?: string;
  /** First playoff week: from here the lines are title odds, not playoff odds. */
  titleFromWeek?: number | null;
}) {
  const data = weeklyHistory(history, titleFromWeek);
  const what = titleFromWeek === null ? "Playoff odds" : "Playoff odds, then title odds from week " + titleFromWeek;
  const teams = historyTeams(odds, history);
  const ordered = [...teams.filter((t) => !t.isMe), ...teams.filter((t) => t.isMe)]; // mine drawn last, on top
  const last = data.length - 1;
  const latest = data[last];
  const mine = teams.find((t) => t.isMe);
  const wide = useMinWidth("lg");
  const named = labeledTeams(latest, teams, wide);
  const shifts = labelShifts(latest, named);
  const maxChars = wide ? END_LABEL_CHARS : PHONE_LABEL_CHARS;
  const endText = (t: Team) => `${clip(t.name, maxChars)} ${formatPercent(valueAt(latest, t.id))}`;
  return (
    <div>
      <div
        className="h-72 w-full"
        role="img"
        aria-describedby={describedBy}
        aria-label={`${what} by week for every team, line chart; the Forest line is the team being viewed`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 16, right: wide ? 150 : 96, bottom: 0, left: 8 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="week" tickFormatter={weekLabel} {...AXIS} padding={{ left: 12, right: 12 }} />
            <YAxis
              domain={[0, 1]}
              ticks={Y_TICKS}
              tickFormatter={(v: number) => formatPercent(v)}
              {...AXIS}
              axisLine={false}
              width={56}
              label={axisCaption(titleFromWeek === null ? "Chance to make playoffs" : "Chance: playoffs, then title")}
            />
            <ReferenceLine y={0.5} stroke={TICK_COLOR} strokeDasharray="4 4" />
            <Tooltip
              cursor={{ stroke: TICK_COLOR, strokeWidth: 1 }}
              content={(p) => (
                <WeekTooltip active={p.active} label={p.label as number | undefined} data={data} teams={teams} marks={marks} />
              )}
              isAnimationActive={false}
            />
            {ordered.map((t) => (
              <Line
                key={t.id}
                dataKey={t.id}
                name={t.name}
                type="linear"
                stroke={t.isMe ? MY_LINE : OTHER_LINE}
                strokeWidth={t.isMe ? 3 : 1.25}
                strokeLinecap="round"
                dot={false}
                activeDot={t.isMe ? { r: 5, fill: MY_LINE, stroke: "var(--lf-page)", strokeWidth: 2 } : false}
                isAnimationActive={false}
                connectNulls
                label={
                  named.some((n) => n.id === t.id) ? (
                    <EndLabel text={endText(t)} last={last} mine={t.isMe} shift={shifts.get(t.id) ?? 0} />
                  ) : undefined
                }
              />
            ))}
            {mine &&
              data.flatMap((p) => {
                const y = valueAt(p, mine.id);
                const notes = marks?.get(p.week);
                if (!notes?.length || y === null) return [];
                const text = notes.length === 1 ? (notes[0]?.short ?? "") : `${notes.length} events`;
                return [
                  <ReferenceDot
                    key={`mark-${p.week}`}
                    x={p.week}
                    y={y}
                    r={5}
                    fill="var(--lf-page)"
                    stroke={MY_LINE}
                    strokeWidth={2}
                    ifOverflow="visible"
                    label={{ value: clip(text, 18), position: "top", offset: 10, fill: TICK_COLOR, fontSize: 11 }}
                  />,
                ];
              })}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <DataTableFallback
        summary="Show odds by week as a table"
        caption={`${what} by week, every team`}
        columns={["Week", ...teams.map((t) => (t.isMe ? `${t.name} (you)` : t.name))]}
        rows={data.map((p) => [weekLabel(p.week), ...teams.map((t) => formatPercent(valueAt(p, t.id)))])}
      />
    </div>
  );
}
