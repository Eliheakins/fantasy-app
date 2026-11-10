import { ApiBoundary } from "@/components/ApiBoundary";
import { useLeagueApi } from "@/lib/league";
import { Explain, formatPercent } from "@/viz";
import { needSentence, needTable } from "./logic";
import type { WinNeedRow } from "./types";

const BAR_WIDTH = 112;
const BAR_HEIGHT = 8;
const NO_TABLE = "Not computed yet: run make refresh to see this.";
const THIN = "Too few simulated seasons behind these numbers to say.";

const needWhy = (wins: number, games: number, row: WinNeedRow) =>
  `Among the ${row.n_runs.toLocaleString("en-US")} simulated seasons where you win ${wins} of your next ${games} (${formatPercent(row.p_condition)} of all seasons), the share in which you make the playoffs.`;

function Line({ wins, games, row }: ReturnType<typeof needTable>[number]) {
  const label = `Win ${wins} of ${games}`;
  return (
    <li className="flex min-h-[44px] flex-wrap items-center gap-x-3">
      <span className="w-24 shrink-0">{label}</span>
      {row === null ? (
        <span className="text-caption text-muted">never happened in the simulated seasons</span>
      ) : (
        <>
          <span className="inline-flex items-center gap-2 whitespace-nowrap">
            <svg aria-hidden="true" width={BAR_WIDTH} height={BAR_HEIGHT} className="shrink-0">
              <rect width={BAR_WIDTH} height={BAR_HEIGHT} rx={2} className="fill-panel-line" />
              <rect width={row.p_playoffs * BAR_WIDTH} height={BAR_HEIGHT} rx={2} className="fill-focus" />
            </svg>
            <span className="w-12 text-right font-semibold tabular-nums">
              <Explain row why={needWhy(wins, games, row)}>
                {formatPercent(row.p_playoffs)}
              </Explain>
            </span>
          </span>
          <span className="text-caption text-muted">{formatPercent(row.p_condition)} of seasons</span>
        </>
      )}
    </li>
  );
}

/** The page's one tinted panel: playoff odds by how many of the next four games are won. */
export function WhatYouNeed() {
  const state = useLeagueApi<WinNeedRow[]>("win-needs");
  return (
    <section aria-labelledby="what-you-need" className="mb-8 key-panel">
      <h2 id="what-you-need" className="text-section font-semibold">
        What you need
      </h2>
      <ApiBoundary state={state}>
        {(rows) => {
          const sentence = needSentence(rows);
          if (rows.length === 0) return <p className="mt-1 text-body text-muted">{NO_TABLE}</p>;
          if (sentence === null) return <p className="mt-1 text-body text-muted">{THIN}</p>;
          return (
            <>
              <p className="measure mt-1 text-body">{sentence}</p>
              <p className="measure text-caption text-muted">
                Playoff odds by wins in your next games, from the same simulated seasons as the odds above.
              </p>
              <ul className="mt-2">
                {needTable(rows).map((l) => (
                  <Line key={l.wins} {...l} />
                ))}
              </ul>
            </>
          );
        }}
      </ApiBoundary>
    </section>
  );
}
