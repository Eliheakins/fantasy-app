import type { League } from "@/api/types";
import { ApiBoundary } from "@/components/ApiBoundary";
import { useApi } from "@/hooks/useApi";
import { Confidence, DataTableFallback, Delta, RangeBar, formatNumber, formatPercent, sharedDomain } from "@/viz";
import { leagueUrl, useRefreshScores } from "./hooks";
import {
  type ActionRow, type LiveScore, type RosterRow, type SeasonOdds, type Unmatched, type WinProbability,
  actionPoints, actionShare, liveScoreText, myOdds, myRange, recordLine, titlePercent, winChance,
} from "./logic";
import { RosterList } from "./RosterList";

const RANGE_WIDTH = 240;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-caption text-muted">{label}</dt>
      <dd className="text-display">{value}</dd>
    </div>
  );
}

function Odds({ rows }: { rows: SeasonOdds[] }) {
  const mine = myOdds(rows);
  if (!mine) return null;
  return (
    <section aria-label="Season odds">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Make playoffs" value={formatPercent(mine.p_playoffs)} />
        <Stat label="First-round bye" value={formatPercent(mine.p_bye)} />
        <Stat label="Win the title" value={titlePercent(mine.p_title)} />
        <Stat label="Expected wins" value={formatNumber(mine.exp_wins)} />
      </dl>
      <p className="mt-1 text-caption text-muted">Odds assume current rosters.</p>
    </section>
  );
}

function LiveScoreSection({ leagueKey }: { leagueKey: string }) {
  const state = useApi<LiveScore[]>(leagueUrl(leagueKey, "live-score"));
  const refresh = useRefreshScores();
  return (
    <section aria-label="Live score" className="space-y-2">
      <button
        type="button"
        onClick={() => refresh.mutate()}
        disabled={refresh.isPending}
        className="min-h-[44px] rounded border border-border bg-surface px-4 text-body"
      >
        {refresh.isPending ? "Refreshing…" : "Refresh scores"}
      </button>
      {refresh.isError && <p role="alert" className="text-body text-warning">Warning: {refresh.error.message}</p>}
      {state.kind === "ready" && state.data.length > 0 && (
        <dl className="grid grid-cols-2 gap-3">
          {state.data.map((r) => (
            <div key={r.side}>
              <dt className="text-caption text-muted">{r.team_name}</dt>
              <dd>{liveScoreText(r)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

function RangeBars({ odds }: { odds: WinProbability }) {
  const mine = myRange(odds);
  const domain = mine ? sharedDomain([mine]) : null;
  if (!mine || !domain) return null;
  return (
    <div className="space-y-1">
      <p className="text-caption text-muted">Team total this week (my lineup)</p>
      <RangeBar {...mine} domain={domain} width={RANGE_WIDTH} height={24} />
      <p className="text-caption text-muted">Opponent range not available yet.</p>
      <DataTableFallback
        columns={["Team", "p10", "Median", "p90"]}
        rows={[["Me", formatNumber(mine.p10), formatNumber(mine.p50), formatNumber(mine.p90)]]}
      />
    </div>
  );
}

function ActionList({ actions, odds }: { actions: ActionRow[]; odds: WinProbability | null }) {
  if (actions.length === 0) {
    return <p className="text-muted">Nothing stands out: your lineup is set and no add moves your odds.</p>;
  }
  return (
    <ol className="space-y-2">
      {actions.map((a) => {
        const points = actionPoints(a.text);
        const share = actionShare(a, odds);
        return (
          <li key={`${a.kind}-${a.text}`} className="flex flex-wrap items-baseline gap-x-2">
            <strong>{a.kind}</strong>
            <span>{a.text}</span>
            {points !== null && <Delta points={points} />}
            {share !== null && <Confidence share={share} />}
          </li>
        );
      })}
    </ol>
  );
}

function Advice({ leagueKey }: { leagueKey: string }) {
  const odds = useApi<WinProbability>(leagueUrl(leagueKey, "win-probability"));
  const actions = useApi<ActionRow[]>(leagueUrl(leagueKey, "actions"));
  const oddsData = odds.kind === "ready" ? odds.data : null;
  const chance = oddsData ? winChance(oddsData) : null;
  return (
    <>
      <ApiBoundary state={odds}>
        {(d) => (
          <section aria-label="This week" className="space-y-2">
            {chance !== null && <Stat label="Chance to win this week" value={formatPercent(chance)} />}
            <RangeBars odds={d} />
          </section>
        )}
      </ApiBoundary>
      <section aria-label="Do this now" className="space-y-2">
        <h3 className="text-body font-semibold">Do this now</h3>
        <ApiBoundary state={actions}>{(a) => <ActionList actions={a} odds={oddsData} />}</ApiBoundary>
      </section>
    </>
  );
}

export function LeagueCard({ league }: { league: League }) {
  const key = league.league_key;
  const odds = useApi<SeasonOdds[]>(leagueUrl(key, "season-odds"));
  const roster = useApi<RosterRow[]>(leagueUrl(key, "roster"));
  const unmatched = useApi<Unmatched>("/api/unmatched");
  return (
    <article className="min-w-0 space-y-4 rounded border border-border p-4">
      <header>
        <h2 className="text-body font-semibold">{league.name} · {league.team_name}</h2>
        <p className="text-caption text-muted">{recordLine(league)}</p>
        <p className="text-caption text-muted">{league.scoring_labels}</p>
      </header>
      {odds.kind === "ready" && <Odds rows={odds.data} />}
      <LiveScoreSection leagueKey={key} />
      <Advice leagueKey={key} />
      <ApiBoundary state={roster}>{(rows) => <RosterList rows={rows} />}</ApiBoundary>
      {unmatched.kind === "ready" && unmatched.data.count > 0 && (
        <p className="text-caption text-muted">{unmatched.data.count} active players have no nflverse history yet.</p>
      )}
    </article>
  );
}
