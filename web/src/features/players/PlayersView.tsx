import { useState } from "react";
import { ApiBoundary } from "@/components/ApiBoundary";
import { RadioGroup } from "@/components/RadioGroup";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { Section } from "@/components/Section";
import type { OutlookRow } from "@/features/outlook/types";
import { useLeagueApi } from "@/lib/league";
import { cn } from "@/lib/utils";
import { Delta, formatNumber, formatPercent } from "@/viz";
import { ALL_POSITIONS, filterByPosition, isOut, PAGE_SIZE, positionsIn, sortByChange } from "./logic";
import { SCOPES, type Scope } from "./scopes";

const CAPTION = "Change is projected points a game over the next four games minus the last four. Sorted by change, biggest gain first.";
const METHOD =
  "Change counts only games the player plays. Improving or Regressing means a change past 1.5 points a game. Three drivers are modeled because they held up in tests on 2019 to 2025: players back from missed games play below projection for a game or two (a player who missed games with no injury report much more), receivers and backs gain when teammates who carry targets or carries are out, and points above or below what usage is worth tend to be partly luck. Usage trends, schedule strength and rookie status added nothing on top of the projection, so they are not used.";
const WHY_MIN_WIDTH = "block min-w-[14rem]";

const radioClass = (on: boolean) =>
  cn("rounded border border-border px-4 text-body", on ? "bg-accent font-semibold text-accent-fg" : "bg-surface text-text");

function columns(showOwner: boolean): Column<OutlookRow>[] {
  return [
    {
      label: "Player",
      role: "primary",
      render: (r) => (
        <>
          {r.full_name} <span className="text-caption font-normal text-muted">{r.position}</span>
        </>
      ),
    },
    ...(showOwner ? [{ label: "Owner", role: "detail" as const, render: (r: OutlookRow) => r.owner }] : []),
    { label: "Outlook", render: (r) => <span className={cn(r.label === "Injured" && "text-warning")}>{r.label}</span> },
    { label: "Last 4 games (pts/g)", numeric: true, role: "detail", render: (r) => formatNumber(r.recent_ppg) },
    { label: "Usage worth (pts/g)", numeric: true, role: "detail", render: (r) => formatNumber(r.expected_ppg) },
    { label: "Next 4 games (pts/g)", numeric: true, render: (r) => formatNumber(r.next_ppg) },
    {
      label: "Change (pts/g)",
      numeric: true,
      render: (r) => <Delta points={r.change ?? Number.NaN} confidence={isOut(r) ? "toss-up" : undefined} />,
    },
    { label: "Plays this game", numeric: true, render: (r) => formatPercent(r.chance_to_play) },
    { label: "Why", role: "detail", render: (r) => <span className={WHY_MIN_WIDTH}>{r.why || "–"}</span> },
  ];
}

/** One scope's rows: position filter, sorted, 25 at a time. Keyed by scope so the page count resets. */
function PlayerTable({ rows, scope }: { rows: readonly OutlookRow[]; scope: Scope }) {
  const [position, setPosition] = useState(ALL_POSITIONS);
  const [shown, setShown] = useState(PAGE_SIZE);
  const positions = positionsIn(rows);
  const filtered = sortByChange(filterByPosition(rows, position));
  const visible = filtered.slice(0, shown);
  return (
    <>
      {positions.length > 2 && (
        <RadioGroup
          label="Position"
          options={positions.map((p) => ({ key: p, label: p === ALL_POSITIONS ? "All positions" : p }))}
          value={position}
          onChange={(p) => { setPosition(p); setShown(PAGE_SIZE); }}
          className="mb-3 flex flex-wrap gap-2"
          optionClassName={radioClass}
        />
      )}
      <ResponsiveTable
        caption="Player outlook"
        columns={columns(scope === "league")}
        rows={visible}
        rowKey={(r, i) => `${r.gsis_id}-${i}`}
      />
      {filtered.length > visible.length && (
        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            className="min-h-[44px] rounded border border-border bg-surface px-4 text-body"
            onClick={() => setShown((n) => n + PAGE_SIZE)}
          >
            Show more
          </button>
          <span className="text-caption text-muted">Showing {visible.length} of {filtered.length}</span>
        </div>
      )}
    </>
  );
}

export function PlayersView() {
  const [scope, setScope] = useState<Scope>("mine");
  const state = useLeagueApi<OutlookRow[]>(`outlook?scope=${scope}`);
  const title = SCOPES.find((s) => s.key === scope)?.label ?? "Players";
  return (
    <>
      <RadioGroup
        label="Players"
        options={SCOPES}
        value={scope}
        onChange={setScope}
        className="mb-6 flex flex-wrap gap-2"
        optionClassName={radioClass}
      />
      <Section title={title} caption={CAPTION} howCalculated={METHOD}>
        <ApiBoundary state={state}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="py-6 text-body text-muted">No players in this group. Try Other rosters.</p>
            ) : (
              <PlayerTable key={scope} rows={rows} scope={scope} />
            )
          }
        </ApiBoundary>
      </Section>
    </>
  );
}
