import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import type { WhatIfRow } from "@/features/league/types";
import { useLeagueApi } from "@/lib/league";
import { Explain, formatNumber } from "@/viz";
import { type RootFor as RootForRow, rootFor } from "./logic";

const swingWhy = (r: RootForRow) =>
  `Your playoff odds if ${r.root} wins minus if ${r.against} wins, each over the simulated seasons where that result happened (at least ${r.runs.toLocaleString("en-US")}). Percentage points.`;

/** Other teams' games this week, ranked by how much each result moves my playoff odds. */
export function RootForSection() {
  const state = useLeagueApi<WhatIfRow[]>("what-if?week=0");
  return (
    <Section title="Who to root for" caption="This week's other games, by how much the result moves your playoff odds.">
      <ApiBoundary state={state}>
        {(rows) => {
          const list = rootFor(rows);
          if (list.length === 0) return <p className="text-body text-muted">No other game this week moves your odds enough to show.</p>;
          return (
            <ol className="max-w-xl">
              {list.map((r) => (
                <li key={r.key} className="flex min-h-[44px] flex-wrap items-center justify-between gap-x-3 border-t border-line first:border-t-0">
                  <span>Root for <strong>{r.root}</strong> <span className="text-muted">over {r.against}</span></span>
                  <span className="whitespace-nowrap"><Explain why={swingWhy(r)}><span className="tabular-nums">{formatNumber(r.swing * 100)}</span></Explain> <span className="text-caption text-muted">pp swing in your playoff odds, from {r.runs.toLocaleString("en-US")} simulated seasons</span></span>
                </li>
              ))}
            </ol>
          );
        }}
      </ApiBoundary>
    </Section>
  );
}
