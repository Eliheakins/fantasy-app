import { useState } from "react";
import { ApiBoundary } from "@/components/ApiBoundary";
import { RadioGroup } from "@/components/RadioGroup";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import type { OutlookRow } from "@/features/outlook/types";
import { useLeagueApi } from "@/lib/league";
import { cn } from "@/lib/utils";
import { Delta, formatNumber, formatPercent } from "@/viz";
import { SCOPES, type Scope } from "./scopes";

const CAPTION =
  "Change is the projected points a game over the next four games (when he plays) minus his last four games. A player is Improving or Regressing past 1.5 points a game. Three drivers are modeled because they held up in tests on 2019 to 2025: players back from missed games play below projection for a game or two (a player who missed games with no injury report much more), receivers and backs gain when teammates who carry targets or carries are out, and points above or below what usage is worth tend to be partly luck. Usage trends, schedule strength and rookie status added nothing on top of the projection, so they are not used.";

const COLUMNS: Column<OutlookRow>[] = [
  { label: "Player", render: (r) => r.full_name },
  { label: "Pos", render: (r) => r.position },
  { label: "Owner", render: (r) => r.owner },
  { label: "Outlook", render: (r) => r.label },
  { label: "Last 4 games", numeric: true, render: (r) => formatNumber(r.recent_ppg) },
  { label: "Usage worth", numeric: true, render: (r) => formatNumber(r.expected_ppg) },
  { label: "Next 4 games", numeric: true, render: (r) => formatNumber(r.next_ppg) },
  { label: "Change", numeric: true, render: (r) => <Delta points={r.change ?? Number.NaN} /> },
  { label: "Plays this game", numeric: true, render: (r) => formatPercent(r.chance_to_play) },
  { label: "Why", render: (r) => r.why },
];

export function PlayersView() {
  const [scope, setScope] = useState<Scope>("mine");
  const state = useLeagueApi<OutlookRow[]>(`outlook?scope=${scope}`);
  return (
    <>
      <RadioGroup
        label="Players"
        options={SCOPES}
        value={scope}
        onChange={setScope}
        className="my-3 flex flex-wrap gap-2"
        optionClassName={(on) =>
          cn("rounded border border-border px-4 text-body", on ? "bg-accent font-semibold text-accent-fg" : "bg-surface text-text")
        }
      />
      <ApiBoundary state={state}>
        {(rows) =>
          rows.length === 0 ? (
            <p className="py-6 text-body text-muted">No players to show.</p>
          ) : (
            <>
              <p className="mb-2 text-caption text-muted">{CAPTION}</p>
              <ResponsiveTable caption="Player outlook" columns={COLUMNS} rows={rows} rowKey={(r, i) => `${r.gsis_id}-${i}`} />
            </>
          )
        }
      </ApiBoundary>
    </>
  );
}
