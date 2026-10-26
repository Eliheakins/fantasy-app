import { WinBar, formatNumber, formatPercent } from "@/viz";
import { rankOdds } from "./logic";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import type { SeasonOddsRow } from "./types";
import type { Who } from "./who";

function columns(who: Who): Column<SeasonOddsRow>[] {
  const marker = who.name ? "(viewed)" : "(you)";
  return [
    { label: "Team", role: "primary", render: (r) => (r.is_me ? `${r.team_name} ${marker}` : r.team_name) },
    { label: "Make playoffs", render: (r) => <WinBar fraction={r.p_playoffs} /> },
    { label: "Win title", numeric: true, render: (r) => formatPercent(r.p_title) },
    { label: "First-round bye", numeric: true, role: "detail", render: (r) => formatPercent(r.p_bye) },
    { label: "Expected wins", numeric: true, role: "detail", render: (r) => formatNumber(r.exp_wins) },
  ];
}

export function OddsTable({ rows, who }: { rows: readonly SeasonOddsRow[]; who: Who }) {
  return (
    <ResponsiveTable
      caption="Season odds by team, ranked by chance to make the playoffs"
      columns={columns(who)}
      rows={rankOdds(rows)}
      rowKey={(r) => String(r.roster_id)}
      isStrong={(r) => r.is_me}
    />
  );
}
