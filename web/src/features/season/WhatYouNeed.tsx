import { ApiBoundary } from "@/components/ApiBoundary";
import { useLeagueApi } from "@/lib/league";
import { formatPercent } from "@/viz";
import { needSentence, needTable } from "./logic";
import type { WinNeedRow } from "./types";

const BAR_WIDTH = 160;
const BAR_HEIGHT = 8;
const NO_TABLE = "Not computed yet: run make refresh to see this.";

function Line({ wins, games, row }: ReturnType<typeof needTable>[number]) {
  const label = `Win ${wins} of ${games}`;
  return (
    <li className="flex min-h-[44px] flex-wrap items-center gap-x-3">
      <span className="w-24 shrink-0">{label}</span>
      {row === null ? (
        <span className="text-caption text-muted">never happened in the simulated seasons</span>
      ) : (
        <>
          <svg role="img" aria-label={`${label}: ${formatPercent(row.p_playoffs)} to make the playoffs`} width={BAR_WIDTH} height={BAR_HEIGHT} className="shrink-0">
            <rect width={BAR_WIDTH} height={BAR_HEIGHT} rx={2} className="fill-panel-line" />
            <rect width={row.p_playoffs * BAR_WIDTH} height={BAR_HEIGHT} rx={2} className="fill-focus" />
          </svg>
          <span className="w-12 text-right font-semibold tabular-nums">{formatPercent(row.p_playoffs)}</span>
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
    <section aria-labelledby="what-you-need" className="mb-8 rounded border border-panel-line bg-panel p-4">
      <h2 id="what-you-need" className="text-heading font-semibold">What you need</h2>
      <ApiBoundary state={state}>
        {(rows) => {
          const sentence = needSentence(rows);
          if (sentence === null) return <p className="mt-1 text-body text-muted">{NO_TABLE}</p>;
          return (
            <>
              <p className="measure mt-1 text-body">{sentence}</p>
              <p className="measure text-caption text-muted">Playoff odds by wins in your next games, from the same simulated seasons as the odds above.</p>
              <ul className="mt-2">{needTable(rows).map((l) => <Line key={l.wins} {...l} />)}</ul>
            </>
          );
        }}
      </ApiBoundary>
    </section>
  );
}
