import { sideName } from "@/lib/scoreboard";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { cn } from "@/lib/utils";
import { WinBar, formatNumber } from "@/viz";
import type { BarTone } from "@/viz/WinBar";
import { barFraction, scheduleOrder } from "./logic";
import type { PowerRankingRow } from "./types";

/** A bar as long as `fraction` of its track; length carries the value. `tone` highlights my row (Forest) against light grey. */
const HBAR_FILL: Record<BarTone | "plain", string> = { mine: "bg-forest", other: "bg-chart-other", plain: "bg-faint" };

export function HBar({ fraction, label, tone }: { fraction: number; label: string; tone?: BarTone }) {
  const fill = HBAR_FILL[tone ?? "plain"];
  return (
    <span role="img" aria-label={label} className="block h-2 w-full rounded-sm bg-line">
      <span className={`block h-2 rounded-sm ${fill}`} style={{ width: `${Math.round(fraction * 100)}%` }} />
    </span>
  );
}

const toneOf = (isMe: boolean): BarTone => (isMe ? "mine" : "other");

export function PowerRankings({ rows }: { rows: readonly PowerRankingRow[] }) {
  const ranked = rows.filter((r) => r.rank != null).sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0));
  const max = Math.max(0, ...ranked.map((r) => r.exp_points_week ?? 0));
  return (
    <ol aria-label="Power rankings by expected points this week" className="space-y-1">
      {ranked.map((r) => (
        <li
          key={r.roster_id}
          className={cn(
            "grid min-h-[44px] max-w-4xl grid-cols-[1.5rem_1fr_3.5rem] items-center gap-x-3 gap-y-1 py-1 md:grid-cols-[1.5rem_14rem_1fr_3.5rem]",
            r.is_me && "font-semibold",
          )}
        >
          <span className="tabular-nums text-muted">{r.rank}</span>
          <span className="truncate">{sideName(r)}</span>
          <span className="col-span-3 col-start-1 row-start-2 md:col-span-1 md:col-start-3 md:row-start-1">
            <HBar
              fraction={barFraction(r.exp_points_week, max)}
              label={`${formatNumber(r.exp_points_week)} expected points`}
              tone={toneOf(r.is_me)}
            />
          </span>
          <span className="col-start-3 row-start-1 text-right tabular-nums md:col-start-4">{formatNumber(r.exp_points_week)}</span>
        </li>
      ))}
    </ol>
  );
}

const SCHEDULE_COLUMNS: Column<PowerRankingRow>[] = [
  { label: "Team", role: "primary", render: (r) => sideName(r) },
  { label: "Rank", numeric: true, render: (r) => r.sos_rank ?? "–" },
  { label: "Opponents' avg. expected points", numeric: true, render: (r) => formatNumber(r.sos_remaining) },
  { label: "Playoff odds", render: (r) => <WinBar fraction={r.p_playoffs} tone={toneOf(r.is_me)} /> },
];

export function ScheduleStrength({ rows }: { rows: readonly PowerRankingRow[] }) {
  return (
    <ResponsiveTable
      caption="Remaining schedule strength"
      columns={SCHEDULE_COLUMNS}
      rows={scheduleOrder(rows)}
      rowKey={(r) => String(r.roster_id)}
      isStrong={(r) => r.is_me}
    />
  );
}
