import type { League } from "@/api/types";
import { ApiBoundary } from "@/components/ApiBoundary";
import { useApi } from "@/hooks/useApi";
import { formatNumber } from "@/viz";
import { Advice } from "./Advice";
import { leagueUrl, useRefreshScores } from "./hooks";
import {
  type LiveScore, type RosterRow, type SeasonOdds, type Unmatched,
  liveScoreParts, myOdds, oddsPercent, recordLine,
} from "./logic";
import { Block, Stat } from "./parts";
import { RosterList } from "./RosterList";

function Odds({ rows }: { rows: SeasonOdds[] }) {
  const mine = myOdds(rows);
  if (!mine) return null;
  return (
    <Block title="Season odds">
      <dl className="grid grid-cols-2 gap-3 @md:grid-cols-4">
        <Stat label="Make playoffs" value={oddsPercent(mine.p_playoffs)} />
        <Stat label="First-round bye" value={oddsPercent(mine.p_bye)} />
        <Stat label="Win the title" value={oddsPercent(mine.p_title)} />
        <Stat label="Expected wins" value={formatNumber(mine.exp_wins)} />
      </dl>
      <p className="mt-1 text-caption text-muted">Odds assume current rosters.</p>
    </Block>
  );
}

function LiveScoreSection({ leagueKey }: { leagueKey: string }) {
  const state = useApi<LiveScore[]>(leagueUrl(leagueKey, "live-score"));
  const refresh = useRefreshScores();
  const button = (
    <button
      type="button"
      onClick={() => refresh.mutate()}
      disabled={refresh.isPending}
      className="min-h-[44px] rounded border border-border px-3 text-caption text-muted"
    >
      {refresh.isPending ? "Refreshing…" : "Refresh scores"}
    </button>
  );
  return (
    <Block title="Live score" action={button}>
      {refresh.isError && <p role="alert" className="text-body text-warning">Warning: {refresh.error.message}</p>}
      {state.kind === "ready" && state.data.length > 0 && (
        <dl className="grid grid-cols-2 gap-3">
          {state.data.map((r) => {
            const p = liveScoreParts(r);
            return (
              <div key={r.side}>
                <dt className="text-caption text-muted">{r.team_name}</dt>
                <dd>
                  <span className="text-heading font-semibold tabular-nums">{p.so_far}</span>{" "}
                  <span className="whitespace-nowrap text-caption text-muted">so far</span>
                  <span className="block whitespace-nowrap text-caption text-muted">projected final {p.projected}</span>
                </dd>
              </div>
            );
          })}
        </dl>
      )}
    </Block>
  );
}

type CardProps = { league: League; mine?: boolean };

export function LeagueCard({ league, mine = true }: CardProps) {
  const key = league.league_key;
  const odds = useApi<SeasonOdds[]>(leagueUrl(key, "season-odds"));
  const roster = useApi<RosterRow[]>(leagueUrl(key, "roster"));
  const unmatched = useApi<Unmatched>("/api/unmatched");
  return (
    <article className="card @container min-w-0">
      <header>
        <h2 className="text-heading font-semibold">{league.name} · {league.team_name}</h2>
        <p className="text-caption text-muted">{recordLine(league)}</p>
        <p className="text-caption text-muted">{league.scoring_labels}</p>
      </header>
      {odds.kind === "ready" && <Odds rows={odds.data} />}
      <LiveScoreSection leagueKey={key} />
      <Advice leagueKey={key} mine={mine} teamName={league.team_name ?? "this team"} />
      <Block title="Roster">
        <ApiBoundary state={roster}>{(rows) => <RosterList rows={rows} />}</ApiBoundary>
      </Block>
      {unmatched.kind === "ready" && unmatched.data.count > 0 && (
        <p className="mt-4 text-caption text-muted">{unmatched.data.count} active players have no nflverse history yet.</p>
      )}
    </article>
  );
}
