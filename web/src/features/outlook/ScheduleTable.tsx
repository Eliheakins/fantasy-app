import { WinBar, formatNumber } from "@/viz";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import type { ScheduleRow } from "./types";
import { type Who, capitalize } from "./who";

function columns(who: Who): Column<ScheduleRow>[] {
  return [
    { label: "Week", role: "primary", numeric: true, render: (r) => `Week ${r.week}` },
    { label: "Opponent", render: (r) => r.opponent },
    { label: `${capitalize(who.you)} (pts)`, numeric: true, render: (r) => formatNumber(r.my_points) },
    { label: "Them (pts)", numeric: true, render: (r) => formatNumber(r.their_points) },
    { label: "Win chance", render: (r) => <WinBar fraction={r.win_chance} /> },
  ];
}

export function ScheduleTable({ rows, who }: { rows: readonly ScheduleRow[]; who: Who }) {
  return (
    <ResponsiveTable caption="Remaining schedule" columns={columns(who)} rows={rows} rowKey={(r) => String(r.week)} />
  );
}
