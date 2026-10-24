import { WinBar, formatNumber } from "@/viz";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import type { ScheduleRow } from "./types";

const COLUMNS: Column<ScheduleRow>[] = [
  { label: "Week", numeric: true, render: (r) => r.week },
  { label: "Opponent", render: (r) => r.opponent },
  { label: "You", numeric: true, render: (r) => formatNumber(r.my_points) },
  { label: "Them", numeric: true, render: (r) => formatNumber(r.their_points) },
  { label: "Win chance", render: (r) => <WinBar fraction={r.win_chance} /> },
];

export function ScheduleTable({ rows }: { rows: readonly ScheduleRow[] }) {
  return (
    <ResponsiveTable caption="Your remaining schedule" columns={COLUMNS} rows={rows} rowKey={(r) => String(r.week)} />
  );
}
