import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { ApiBoundary } from "@/components/ApiBoundary";
import { RadioGroup } from "@/components/RadioGroup";
import { useLeague, useLeagueApi } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";
import { usePageEyebrow, useWeek } from "@/lib/week";
import type { ScoreboardRow } from "@/features/scoreboard/logic";
import { ChevronDown } from "lucide-react";
import { Explain, ExplainDelta, NOISE_PERCENT, formatNumber, formatPercent } from "@/viz";
import { CloseCalls } from "@/features/lineup/CloseCalls";
import { ResultPanel } from "@/features/lineup/ResultPanel";
import { OPTION_OF, recommendedObjective, slotCalls, startAnswer, weekOverText, weekResult } from "@/features/lineup/calls";
import { SLEEPER_WIN_WHY, winChanceWhy } from "@/features/lineup/explain";
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
  labelOf,
  headline,
  lineupsDiffer,
  rowsFor,
  sleeperKnown,
  splitLineup,
} from "@/features/lineup/logic";

/** `shown` is the team total with K and DEF, like the range bars; without the simulation it is the skill slots only. */
function Answer({ shown, skillOnly, win, sleeperWin, option }: { shown: number; skillOnly: boolean; win: number | null; sleeperWin: number | null; option: WinProbability["options"][number] | undefined }) {
  const change = win !== null && sleeperWin !== null ? (win - sleeperWin) * 100 : null;
  return (
    <>
      This lineup projects <strong className="font-semibold">{formatNumber(shown)} points</strong>{skillOnly && " from the skill slots"}
      {win !== null && <> and has a <Explain why={winChanceWhy(option)}><strong className="font-semibold">{formatPercent(win)}</strong></Explain> chance to win</>}
      {change !== null && <> (<ExplainDelta points={change} noise={NOISE_PERCENT} why={SLEEPER_WIN_WHY} /> points against what is set in Sleeper now)</>}.
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
  const result = weekResult(board);
  const sleeperOption = odds?.options.find((o) => o.option === "sleeper_now");
  return (
    <div className="max-w-[960px]">
      <PageHeader
        title={over ?? startAnswer(rows, known)}
        eyebrow={eyebrow}
        answer={over
          ? "Every game is final, so there is nothing left to set."
          : <Answer shown={shownOption?.expected_points ?? h.shown} skillOnly={!shownOption} win={h.win} sleeperWin={sleeperOption?.win_prob ?? null} option={shownOption} />}
      />
      <ResultPanel result={result} option={shownOption} win={hasOdds ? h.win : null} shown={h.shown} now={h.now} gap={h.gap} />
      <CloseCalls calls={slotCalls(odds, objective)} rows={rows} objective={objective} />
      {hasOdds && !result && (
        <details className="group mt-8">
          <summary className="no-chevron inline-flex min-h-[44px] cursor-pointer list-none items-center gap-2 rounded-full border border-panel-line bg-white px-4 font-medium text-ink hover:bg-panel [&::-webkit-details-marker]:hidden">
            Other ways to pick
            <ChevronDown aria-hidden size={16} className="text-muted transition-transform group-open:rotate-180" />
          </summary>
          <p className="mt-2 text-caption text-muted">Optimize for expected points, win chance, ceiling or floor, and compare what each would start.</p>
          {odds.script && (
            <p className="mt-4 text-body">{odds.script}. We start from {labelOf(recommended)}{chosen ? ` (showing ${labelOf(chosen)})` : ""}.</p>
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
      <div className="mt-10">
        <PlayerTable
          title="Start"
          rows={start}
          known={known}
          final={result !== null}
          caption={result ? "Every game is final: points scored this week." : "Points are for this week; the bar is the 10 to 90% range with the median marked."}
          howCalculated={CAVEAT_BASE + (known ? "" : CAVEAT_UNKNOWN)}
        />
      </div>
      {bench.length > 0 && <PlayerTable title="Bench" rows={bench} known={known} final={result !== null} />}
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
