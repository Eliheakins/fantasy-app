import type { ReactNode } from "react";
import { Explain, ExplainDelta, formatNumber, formatPercent } from "@/viz";
import { type WeekResult, resultText } from "./calls";
import { SLEEPER_POINTS_WHY, winChanceWhy } from "./explain";
import { type WinProbability, gapIsNoise } from "./logic";
import { TeamRanges } from "./TeamRanges";

type Option = WinProbability["options"][number];

function Stat({ label, children, note }: { label: string; children: ReactNode; note?: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-caption text-label">{label}</dt>
      <dd className="mt-1 text-[22px] font-semibold leading-7 text-ink md:text-[28px] md:leading-9">{children}</dd>
      {note && <dd className="text-caption text-muted">{note}</dd>}
    </div>
  );
}

type Props = {
  result: WeekResult | null;
  option: Option | undefined;
  win: number | null;
  shown: number;
  now: number | null;
  gap: number | null;
};

/** The page's one tinted panel: both team totals, the chance to win (or the final result), the lineup against Sleeper. */
export function ResultPanel({ result, option, win, shown, now, gap }: Props) {
  const sleeperNote = gap === null ? null : gapIsNoise(gap) ? "Sleeper's lineup is the same" : <>Sleeper's lineup: <ExplainDelta points={gap} why={SLEEPER_POINTS_WHY} /></>;
  return (
    <section aria-labelledby="matchup-heading" className="key-panel">
      <h2 id="matchup-heading" className="text-caption font-semibold uppercase tracking-wide text-focus">Your matchup</h2>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-4">
        {result ? (
          <>
            <Stat label="You, final">{formatNumber(result.me)}</Stat>
            <Stat label="Opponent, final">{formatNumber(result.them)}</Stat>
            <Stat label="Result">{resultText(result)}</Stat>
          </>
        ) : (
          option && (
            <>
              <Stat label="You, median">{formatNumber(option.median)}</Stat>
              <Stat label="Opponent, median">{formatNumber(option.opp_median)}</Stat>
              {win !== null && <Stat label="Chance to win"><Explain why={winChanceWhy(option)}>{formatPercent(win)}</Explain></Stat>}
            </>
          )
        )}
        <Stat label={now === null ? "Skill slots, projected" : "Skill slots, shown vs Sleeper"} note={sleeperNote}>
          {formatNumber(shown)}
          {now !== null && <span className="text-heading font-normal text-muted"> vs {formatNumber(now)}</span>}
        </Stat>
      </dl>
      {!result && option && (
        <div className="mt-5 border-t border-panel-line pt-4">
          <p className="text-caption text-label">Where each team's week lands: the bar is the 10 to 90% range, the mark is the median.</p>
          <TeamRanges option={option} />
        </div>
      )}
    </section>
  );
}
