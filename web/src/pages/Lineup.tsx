import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { ApiBoundary } from "@/components/ApiBoundary";
import { RadioGroup } from "@/components/RadioGroup";
import { useLeague, useLeagueApi } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";
import { usePageEyebrow, useWeek } from "@/lib/week";
import { Section } from "@/components/Section";
import type { ScoreboardRow } from "@/features/scoreboard/logic";
import { Delta, NOISE_PERCENT, formatNumber, formatPercent } from "@/viz";
import { CloseCalls } from "@/features/lineup/CloseCalls";
import { TeamRanges } from "@/features/lineup/TeamRanges";
import { OPTION_OF, recommendedObjective, slotCalls, startAnswer, weekOverText } from "@/features/lineup/calls";
import { Comparison } from "@/features/lineup/Comparison";
import { PlayerTable } from "@/features/lineup/PlayerTables";
import {
  CAVEAT_BASE,
  CAVEAT_UNKNOWN,
  NO_SWAP_TEXT,
  OBJECTIVES,
  type LineupRow,
  type ObjectiveKey,
  type WinProbability,
  gapIsNoise,
  labelOf,
  headline,
  lineupsDiffer,
  rowsFor,
  sleeperKnown,
  splitLineup,
} from "@/features/lineup/logic";

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-caption text-muted">{label}</div>
      <div className="text-heading font-semibold tabular-nums">{children}</div>
    </div>
  );
}

/** `shown` is the team total with K and DEF, like the range bars; without the simulation it is the skill slots only. */
function Answer({ shown, skillOnly, win, sleeperWin }: { shown: number; skillOnly: boolean; win: number | null; sleeperWin: number | null }) {
  const change = win !== null && sleeperWin !== null ? (win - sleeperWin) * 100 : null;
  return (
    <>
      This lineup projects <strong className="font-semibold">{formatNumber(shown)} points</strong>{skillOnly && " from the skill slots"}
      {win !== null && <> and has a <strong className="font-semibold">{formatPercent(win)}</strong> chance to win</>}
      {change !== null && <> (<Delta points={change} noise={NOISE_PERCENT} /> points against what is set in Sleeper now)</>}.
    </>
  );
}

type ViewProps = { base: LineupRow[]; odds: WinProbability | null; week: number; eyebrow?: string; board?: ScoreboardRow[] | null };

export function LineupView({ base, odds, week, eyebrow, board = null }: ViewProps) {
  // a manual pick belongs to the label it was made under: when the label flips, the default returns
  const [picked, setPicked] = useState<{ key: ObjectiveKey; under: ObjectiveKey } | null>(null);
  if (base.length === 0) {
    return (
      <>
        <PageHeader title="Lineup" eyebrow={eyebrow} />
        <p className="py-6 text-body text-muted">
          No projections for week {week}: either a past week or your players are on bye.
        </p>
      </>
    );
  }
  const hasOdds = odds !== null && odds.options.length > 0;
  const recommended = recommendedObjective(odds?.script);
  const differ = hasOdds && lineupsDiffer(odds.comparison);
  const chosen = differ && picked?.under === recommended ? picked.key : null;
  const objective = chosen ?? recommended;
  const rows = rowsFor(base, odds, objective);
  const { start, bench } = splitLineup(rows);
  const known = sleeperKnown(rows);
  const h = headline(rows, odds?.summaries[objective]);
  const shownOption = odds?.options.find((o) => o.option === OPTION_OF[objective]);
  const over = weekOverText(week, board);
  const sleeperOption = odds?.options.find((o) => o.option === "sleeper_now");
  return (
    <div>
      <PageHeader
        title={over ?? startAnswer(rows, known)}
        eyebrow={eyebrow}
        answer={over
          ? "Every game is final, so there is nothing left to set."
          : <Answer shown={shownOption?.expected_points ?? h.shown} skillOnly={!shownOption} win={h.win} sleeperWin={sleeperOption?.win_prob ?? null} />}
      />
      <CloseCalls calls={slotCalls(odds, objective)} rows={rows} objective={objective} />
      {shownOption && (
        <Section title="Team scores" caption="Where each team's week lands: the bar is the 10 to 90% range, the mark is the median.">
          <TeamRanges option={shownOption} />
        </Section>
      )}
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Metric label="Lineup shown, skill slots">{formatNumber(h.shown)} pts</Metric>
        {h.now !== null && (
          <Metric label="Set in Sleeper now, skill slots">
            {formatNumber(h.now)} pts{" "}
            {h.gap !== null && (gapIsNoise(h.gap)
              ? <span className="text-caption font-normal text-muted">same as shown</span>
              : <Delta points={h.gap} className="text-body" />)}
          </Metric>
        )}
        {hasOdds && h.win !== null && <Metric label="Chance to win">{formatPercent(h.win)}</Metric>}
      </div>
      {hasOdds && (
        <details className="mt-6">
          <summary className="flex min-h-[44px] cursor-pointer items-center text-heading font-semibold">Other ways to pick</summary>
          {odds.script && (
            <p className="text-body">{odds.script}. We start from {labelOf(recommended)}{chosen ? ` (showing ${labelOf(chosen)})` : ""}.</p>
          )}
          {differ && (
            <RadioGroup
              label="Optimize for"
              options={OBJECTIVES}
              value={objective}
              onChange={(key) => setPicked({ key, under: recommended })}
              className="mt-3 flex flex-wrap gap-2"
              optionClassName={(on) => `rounded-full border px-3 text-body ${on ? "border-focus bg-focus font-medium text-white" : "border-panel-line bg-panel"}`}
            />
          )}
          {odds.swap?.differs && odds.swap.text && (
            <p role="note" className="mt-4 rounded-xl border border-line p-4 text-body text-label">{odds.swap.text}</p>
          )}
          {odds.swap && !odds.swap.differs && <p className="mt-4 text-caption text-muted">{NO_SWAP_TEXT}</p>}
          <div className="mt-4"><Comparison rows={odds.comparison} /></div>
        </details>
      )}
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
  const { league } = useLeague();
  const { week } = useWeek();
  const eyebrow = usePageEyebrow("Lineup", true);
  const lineup = useLeagueApi<LineupRow[]>(`lineup?week=${week}`);
  const odds = useLeagueApi<WinProbability>(`win-probability?week=${week}`);
  const board = useLeagueApi<ScoreboardRow[]>(`scoreboard?week=${week}`);
  const { team } = useTeam();
  return (
    <div key={league}>
      {lineup.kind !== "ready" && <PageHeader title="Lineup" eyebrow={eyebrow} />}
      <ApiBoundary state={lineup}>
        {(base) => (
          <>
            {odds.kind === "running" && (
              <p role="status" className="mt-3 text-caption text-muted">
                Win probabilities are still being simulated. Showing expected points for now.
              </p>
            )}
            <LineupView key={`${league}|${team}|${week}`} base={base} odds={odds.kind === "ready" ? odds.data : null} week={week} eyebrow={eyebrow} board={board.kind === "ready" ? board.data : null} />
          </>
        )}
      </ApiBoundary>
    </div>
  );
}
