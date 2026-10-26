import { PageHeader } from "@/components/PageHeader";
import { useState } from "react";
import { ApiBoundary } from "@/components/ApiBoundary";
import { RadioGroup } from "@/components/RadioGroup";
import { useLeague, useLeagueApi } from "@/lib/league";
import { Delta, formatNumber, formatPercent } from "@/viz";
import { Comparison } from "@/features/lineup/Comparison";
import { PlayerTable } from "@/features/lineup/PlayerTables";
import {
  CAVEAT_BASE,
  CAVEAT_UNKNOWN,
  LAST_WEEK,
  NO_SWAP_TEXT,
  OBJECTIVES,
  type LineupRow,
  type ObjectiveKey,
  type WinProbability,
  gapIsNoise,
  headline,
  lineupsDiffer,
  rowsFor,
  sleeperKnown,
  splitLineup,
} from "@/features/lineup/logic";

const WEEKS = Array.from({ length: LAST_WEEK }, (_, i) => i + 1);

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-caption text-muted">{label}</div>
      <div className="text-heading font-semibold tabular-nums">{children}</div>
    </div>
  );
}

export function LineupView({ base, odds, week }: { base: LineupRow[]; odds: WinProbability | null; week: number }) {
  const [objective, setObjective] = useState<ObjectiveKey>("expected_points");
  if (base.length === 0) {
    return (
      <p className="py-6 text-body text-muted">
        No projections for week {week}: either a past week or your players are on bye.
      </p>
    );
  }
  const hasOdds = odds !== null && odds.options.length > 0;
  const rows = rowsFor(base, odds, objective);
  const { start, bench } = splitLineup(rows);
  const known = sleeperKnown(rows);
  const h = headline(rows, odds?.summaries[objective]);
  const differ = hasOdds && lineupsDiffer(odds.comparison);
  return (
    <div>
      {odds?.script && <p className="text-body font-semibold">{odds.script}</p>}
      {differ && (
        <RadioGroup
          label="Optimize for"
          options={OBJECTIVES}
          value={objective}
          onChange={setObjective}
          className="mt-3 flex flex-wrap gap-2"
          optionClassName={(on) => `rounded-md border px-3 text-body ${on ? "border-ring bg-border font-medium" : "border-border"}`}
        />
      )}
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Metric label="Lineup shown">{formatNumber(h.shown)} pts</Metric>
        {h.now !== null && (
          <Metric label="Set in Sleeper now">
            {formatNumber(h.now)} pts{" "}
            {h.gap !== null && (gapIsNoise(h.gap)
              ? <span className="text-caption font-normal text-muted">same as shown</span>
              : <Delta points={h.gap} className="text-body" />)}
          </Metric>
        )}
        {hasOdds && h.win !== null && <Metric label="Chance to win">{formatPercent(h.win)}</Metric>}
      </div>
      {hasOdds && odds.swap?.differs && odds.swap.text && (
        <p role="note" className="mt-4 card-flat text-body">{odds.swap.text}</p>
      )}
      {hasOdds && odds.swap && !odds.swap.differs && <p className="mt-4 text-caption text-muted">{NO_SWAP_TEXT}</p>}
      {hasOdds && <div className="mt-8"><Comparison rows={odds.comparison} /></div>}
      <div className="mt-8">
        <PlayerTable
          title="Start"
          rows={start}
          known={known}
          caption="Points are for this week; the bar is the 10 to 90% range with the median marked."
          howCalculated={CAVEAT_BASE + (known ? "" : CAVEAT_UNKNOWN)}
        />
      </div>
      {bench.length > 0 && <PlayerTable title="Bench" rows={bench} known={known} />}
    </div>
  );
}

export default function Lineup() {
  const { league, leagues } = useLeague();
  // Keyed by league so a week picked in one league does not carry to the other.
  const [picked, setPicked] = useState<{ league: string | null; week: number } | null>(null);
  const current = leagues.kind === "ready" ? leagues.data.find((l) => l.league_key === league)?.current_week : null;
  const week = (picked?.league === league ? picked.week : null) ?? current ?? 1;
  const lineup = useLeagueApi<LineupRow[]>(`lineup?week=${week}`);
  const odds = useLeagueApi<WinProbability>(`win-probability?week=${week}`);
  return (
    <div key={league}>
      <PageHeader
        title="Lineup"
        actions={
        <label className="flex items-center gap-2 text-body">
          Week
          <select
            value={week}
            onChange={(e) => setPicked({ league, week: Number(e.target.value) })}
            className="min-h-[44px] rounded-md border border-border bg-transparent px-2"
          >
            {WEEKS.map((w) => (
              <option key={w} value={w}>{w}</option>
            ))}
          </select>
        </label>
        }
      />
      <ApiBoundary state={lineup}>
        {(base) => (
          <>
            {odds.kind === "running" && (
              <p role="status" className="mt-3 text-caption text-muted">
                Win probabilities are still being simulated. Showing expected points for now.
              </p>
            )}
            <LineupView base={base} odds={odds.kind === "ready" ? odds.data : null} week={week} />
          </>
        )}
      </ApiBoundary>
    </div>
  );
}
