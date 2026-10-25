import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { cn } from "@/lib/utils";
import { WinBar, formatNumber } from "@/viz";
import { barFraction, scheduleOrder } from "./logic";
import type { PowerRankingRow } from "./types";

/** A grey bar, as long as `fraction` of its track. Length carries the value; there is no colour. */
export function HBar({ fraction, label }: { fraction: number; label: string }) {
  return (
    <span role="img" aria-label={label} className="block h-2 w-full rounded-sm bg-border">
      <span className="block h-2 rounded-sm bg-range" style={{ width: `${Math.round(fraction * 100)}%` }} />
    </span>
  );
}

export function PowerRankings({ rows }: { rows: readonly PowerRankingRow[] }) {
  const ranked = rows.filter((r) => r.rank != null).sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0));
  const max = Math.max(0, ...ranked.map((r) => r.exp_points_week ?? 0));
  return (
    <ol aria-label="Power rankings by expected points this week" className="space-y-1">
      {ranked.map((r) => (
        <li
          key={r.roster_id}
          className={cn(
            "grid min-h-[44px] grid-cols-[1.5rem_1fr_3.5rem] items-center gap-x-2 gap-y-1 border-l-4 border-transparent px-2 py-1 md:grid-cols-[1.5rem_14rem_1fr_3.5rem]",
            r.is_me && "border-l-accent font-semibold",
          )}
        >
          <span className="tabular-nums text-muted">{r.rank}</span>
          <span className="truncate">{r.is_me ? `${r.team_name} (you)` : r.team_name}</span>
          <span className="col-span-3 col-start-1 row-start-2 md:col-span-1 md:col-start-3 md:row-start-1">
            <HBar fraction={barFraction(r.exp_points_week, max)} label={`${formatNumber(r.exp_points_week)} expected points`} />
          </span>
          <span className="col-start-3 row-start-1 text-right tabular-nums md:col-start-4">{formatNumber(r.exp_points_week)}</span>
        </li>
      ))}
    </ol>
  );
}

const SCHEDULE_COLUMNS: Column<PowerRankingRow>[] = [
  { label: "Team", role: "primary", render: (r) => `${r.sos_rank ?? "–"}. ${r.is_me ? `${r.team_name} (you)` : r.team_name}` },
  { label: "Opponents' avg. expected points", numeric: true, render: (r) => formatNumber(r.sos_remaining) },
  { label: "Playoffs", render: (r) => <WinBar fraction={r.p_playoffs} /> },
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
