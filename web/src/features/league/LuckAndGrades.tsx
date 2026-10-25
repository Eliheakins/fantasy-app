import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { Delta, formatNumber, formatPercent } from "@/viz";
import { HBar } from "./PowerRankings";
import { formatRecord } from "./logic";
import type { LuckRow, ManagerGradeRow } from "./types";

const name = (r: { team_name: string; is_me: boolean }) => (r.is_me ? `${r.team_name} (you)` : r.team_name);

const LUCK_COLUMNS: Column<LuckRow>[] = [
  { label: "Team", role: "primary", render: name },
  { label: "Record", numeric: true, render: (r) => formatRecord(r.wins, r.losses, r.ties) },
  { label: "All-play", numeric: true, render: (r) => formatRecord(r.ap_wins, r.ap_losses, r.ap_ties) },
  { label: "Expected wins", numeric: true, render: (r) => formatNumber(r.exp_wins) },
  { label: "Luck (wins)", numeric: true, render: (r) => <Delta points={r.luck} /> },
];

export function LuckTable({ rows }: { rows: readonly LuckRow[] }) {
  return (
    <ResponsiveTable
      caption="Luck: actual wins against the all-play record"
      columns={LUCK_COLUMNS}
      rows={rows}
      rowKey={(r) => String(r.roster_id)}
      isStrong={(r) => r.is_me}
    />
  );
}

const GRADE_COLUMNS: Column<ManagerGradeRow>[] = [
  { label: "Team", role: "primary", render: name },
  {
    label: "Efficiency",
    render: (r) => (
      <span className="flex items-center gap-2">
        <span className="w-24"><HBar fraction={r.efficiency} label={`Efficiency ${formatPercent(r.efficiency)}`} /></span>
        <span className="tabular-nums">{formatPercent(r.efficiency)}</span>
      </span>
    ),
  },
  { label: "Started", numeric: true, render: (r) => formatNumber(r.actual_points) },
  { label: "Best possible", numeric: true, render: (r) => formatNumber(r.optimal_points) },
  { label: "Left on bench", numeric: true, render: (r) => formatNumber(r.bench_points_left) },
];

export function GradesTable({ rows }: { rows: readonly ManagerGradeRow[] }) {
  return (
    <ResponsiveTable
      caption="Manager grades: points started against the best lineup in hindsight"
      columns={GRADE_COLUMNS}
      rows={rows}
      rowKey={(r) => String(r.roster_id)}
      isStrong={(r) => r.is_me}
    />
  );
}
