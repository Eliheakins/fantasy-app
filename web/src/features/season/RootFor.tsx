import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import type { WhatIfRow } from "@/features/league/types";
import { useLeagueApi } from "@/lib/league";
import { rootFor } from "./logic";

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
                  <span className="whitespace-nowrap"><span className="tabular-nums">{(r.swing * 100).toFixed(1)}</span> <span className="text-caption text-muted">pp swing in your playoff odds</span></span>
                </li>
              ))}
            </ol>
          );
        }}
      </ApiBoundary>
    </Section>
  );
}
