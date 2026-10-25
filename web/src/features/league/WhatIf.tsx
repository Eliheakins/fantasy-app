import { useState } from "react";
import { ApiBoundary } from "@/components/ApiBoundary";
import { RadioGroup } from "@/components/RadioGroup";
import { useLeague, useLeagueApi } from "@/lib/league";
import { cn } from "@/lib/utils";
import { Delta, formatPercent } from "@/viz";
import { MIN_RUNS, type Matchup, groupMatchups, isThin } from "./logic";
import type { WhatIfRow } from "./types";

const WEEKS_AHEAD = 4;
const OPTION_CLASS = (on: boolean) =>
  cn("rounded border border-border px-4 text-body", on ? "bg-accent font-semibold text-accent-fg" : "bg-surface text-text");

/** Odds change in percentage points, so the shared Delta formatting applies. */
const points = (fraction: number) => fraction * 100;

function Outcome({ row }: { row: WhatIfRow }) {
  const runs = row.n_runs.toLocaleString("en-US");
  if (isThin(row)) {
    return (
      <p className="mt-3 text-body text-muted">
        Hidden: {row.winner} beating {row.loser} happened in only {runs} of the simulated seasons (under{" "}
        {MIN_RUNS.toLocaleString("en-US")}), so the odds behind it are too noisy to show.
      </p>
    );
  }
  return (
    <div className="mt-3">
      <p className="text-caption text-muted">
        If {row.winner} beats {row.loser} ({formatPercent(row.p_condition)} of runs, n = {runs}), your odds change by:
      </p>
      <dl className="mt-1 grid max-w-xs grid-cols-2 gap-y-1 text-body">
        <dt>Playoffs (points)</dt>
        <dd className="text-right"><Delta points={points(row.d_playoffs)} /></dd>
        <dt>Title (points)</dt>
        <dd className="text-right"><Delta points={points(row.d_title)} /></dd>
      </dl>
    </div>
  );
}

function Picker({ matchups }: { matchups: readonly Matchup[] }) {
  const [matchupKey, setMatchupKey] = useState(matchups[0]?.key ?? "");
  const [outcomeIndex, setOutcomeIndex] = useState(0);
  const matchup = matchups.find((m) => m.key === matchupKey) ?? matchups[0];
  if (!matchup) return null;
  const outcome = matchup.outcomes[outcomeIndex] ?? matchup.outcomes[0];
  return (
    <div>
      <label className="block text-caption text-muted" htmlFor="what-if-matchup">Matchup</label>
      <select
        id="what-if-matchup"
        value={matchup.key}
        onChange={(e) => { setMatchupKey(e.target.value); setOutcomeIndex(0); }}
        className="min-h-[44px] w-full max-w-sm rounded border border-border bg-surface px-2 text-body"
      >
        {matchups.map((m) => (
          <option key={m.key} value={m.key}>{m.involvesMe ? `${m.label} (yours)` : m.label}</option>
        ))}
      </select>
      <RadioGroup
        label="Outcome"
        options={matchup.outcomes.map((o, i) => ({ key: String(i), label: `${o.winner} wins` }))}
        value={String(outcomeIndex)}
        onChange={(k) => setOutcomeIndex(Number(k))}
        className="mt-2 flex flex-wrap gap-2"
        optionClassName={OPTION_CLASS}
      />
      {outcome && <Outcome row={outcome} />}
    </div>
  );
}

export function WhatIf() {
  const { leagues, league } = useLeague();
  const current = leagues.kind === "ready" ? leagues.data.find((l) => l.league_key === league)?.current_week : null;
  const [ahead, setAhead] = useState(0);
  const week = current == null ? 0 : current + ahead;
  const state = useLeagueApi<WhatIfRow[]>(`what-if?week=${week}`);
  const options = Array.from({ length: WEEKS_AHEAD }, (_, i) => ({
    key: String(i),
    label: current == null ? "This week" : `Week ${current + i}`,
  }));
  return (
    <div>
      {current != null && (
        <RadioGroup
          label="Week"
          options={options}
          value={String(ahead)}
          onChange={(k) => setAhead(Number(k))}
          className="mb-3 flex flex-wrap gap-2"
          optionClassName={OPTION_CLASS}
        />
      )}
      <ApiBoundary state={state}>
        {(rows) => {
          const matchups = groupMatchups(rows);
          return matchups.length === 0 ? (
            <p className="py-3 text-body text-muted">No matchups to test for this week.</p>
          ) : (
            <Picker key={week} matchups={matchups} />
          );
        }}
      </ApiBoundary>
    </div>
  );
}
