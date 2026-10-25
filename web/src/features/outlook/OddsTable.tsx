import { WinBar, formatNumber, formatPercent } from "@/viz";
import { rankOdds } from "./logic";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import type { SeasonOddsRow } from "./types";

const COLUMNS: Column<SeasonOddsRow>[] = [
  { label: "Team", role: "primary", render: (r) => (r.is_me ? `${r.team_name} (you)` : r.team_name) },
  { label: "Playoffs", render: (r) => <WinBar fraction={r.p_playoffs} /> },
  { label: "Bye", numeric: true, render: (r) => formatPercent(r.p_bye) },
  { label: "Title", numeric: true, render: (r) => formatPercent(r.p_title) },
  { label: "Exp. wins", numeric: true, render: (r) => formatNumber(r.exp_wins) },
];

export function OddsTable({ rows }: { rows: readonly SeasonOddsRow[] }) {
  return (
    <ResponsiveTable
      caption="Season odds by team"
      columns={COLUMNS}
      rows={rankOdds(rows)}
      rowKey={(r) => String(r.roster_id)}
      isStrong={(r) => r.is_me}
    />
  );
}
