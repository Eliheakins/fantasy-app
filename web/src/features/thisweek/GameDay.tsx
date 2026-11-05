import { useQuery } from "@tanstack/react-query";
import { fetchEnvelope, resolveState } from "@/api/envelope";
import type { components } from "@/api/schema";
import type { League, Status } from "@/api/types";
import { leagueUrl, useHomeLeagues } from "@/features/home/hooks";
import { useApi } from "@/hooks/useApi";
import { possessive } from "@/lib/text";
import { Explain, formatNumber, formatPercent } from "@/viz";
import { isDecided, neededLine, players } from "./gameDayText";
import { WinChanceLine } from "./WinChanceLine";

type GameDayData = components["schemas"]["GameDayData"];
const MS_PER_MINUTE = 60_000;
const STATUS_POLL_MS = MS_PER_MINUTE; // the block appears and goes away within a minute of the games
const FALLBACK_TICK_MINUTES = 10; // the live refresh's own interval, if the status does not say

/** Whether a game of the week is on (the live refresh's own switch) and how often it ticks. Shares the /api/status query with the top bar. */
export function useLiveStatus(): { live: boolean; intervalMs: number } {
  const state = useApi<Status>("/api/status", STATUS_POLL_MS);
  const live = state.kind === "ready" ? state.data.live_refresh : null;
  return {
    live: Boolean(live?.enabled && live.active),
    intervalMs: (live?.interval_minutes ?? FALLBACK_TICK_MINUTES) * MS_PER_MINUTE,
  };
}

function useGameDay(leagueKey: string, intervalMs: number) {
  const url = leagueUrl(leagueKey, "game-day");
  const q = useQuery({
    queryKey: ["api", url],
    queryFn: () => fetchEnvelope<GameDayData>(url),
    refetchInterval: intervalMs,
    retry: 1,
  });
  const stale = Boolean(q.data && q.error); // a failed refetch keeps the last update on screen
  return { state: resolveState(q.data, stale ? null : q.error), stale };
}

type Now = NonNullable<GameDayData["current"]>;
const winWhy = (c: Now) =>
  `Share of simulated finishes of this week's matchup in which your total beats ${possessive(c.opp_team)}, counting points already scored. Projected finals: ${c.my_team} ${formatNumber(c.my_projected)}, ${c.opp_team} ${formatNumber(c.opp_projected)}; ${players(c.my_left)} for you, ${players(c.opp_left)} for them.`;

function LeagueGameDay({ league, intervalMs }: { league: League; intervalMs: number }) {
  const { state, stale } = useGameDay(league.league_key, intervalMs);
  const name = league.name?.trim() || league.league_key;
  if (state.kind === "error") return <p role="alert" className="text-body text-warning">{name}: game-day numbers did not load.</p>;
  if (state.kind !== "ready") return <p role="status" className="text-muted">{name}: loading…</p>;
  const { current: c, history, as_of } = state.data;
  if (!c) return <p className="text-body text-muted">{name}: no matchup in play this week.</p>;
  return (
    <div className="border-t border-panel-line pt-3">
      <h3 className="text-body font-semibold">{name}: {c.my_team} vs {c.opp_team}</h3>
      {stale && <p role="status" className="text-caption text-warning">The last refresh failed; these are the previous numbers.</p>}
      {!isDecided(c) && (
        <p className="mt-1 text-body">
          <Explain why={winWhy(c)}><span className="text-heading font-semibold tabular-nums">{formatPercent(c.win_prob)}</span></Explain> chance to win
        </p>
      )}
      <ul className="mt-1 space-y-0.5 text-body tabular-nums">
        <li>{c.my_team}: {formatNumber(c.my_points)} so far, projected {formatNumber(c.my_projected)}, {players(c.my_left)}</li>
        <li>{c.opp_team}: {formatNumber(c.opp_points)} so far, projected {formatNumber(c.opp_projected)}, {players(c.opp_left)}</li>
        <li>{neededLine(c)}</li>
      </ul>
      <div className="mt-2"><WinChanceLine history={history} now={as_of ? { at: as_of, win_prob: c.win_prob } : null} /></div>
    </div>
  );
}

/** The game-day panel at the top of This week while a game is on: the page's tinted panel then. */
export function GameDay({ intervalMs }: { intervalMs: number }) {
  const leagues = useHomeLeagues();
  const list = leagues.kind === "ready" ? leagues.data : [];
  return (
    <section aria-labelledby="gameday-heading" className="mb-6 key-panel">
      <h2 id="gameday-heading" className="mb-3 text-section font-semibold">Game day: a game is on</h2>
      {leagues.kind === "error" && <p role="alert" className="text-body text-warning">The leagues did not load, so there are no game-day numbers.</p>}
      {(leagues.kind === "loading" || leagues.kind === "running") && <p role="status" className="text-muted">Loading leagues…</p>}
      <div className="flex flex-col gap-4">
        {list.map((l) => <LeagueGameDay key={l.league_key} league={l} intervalMs={intervalMs} />)}
      </div>
      <p className="mt-3 text-caption text-muted">Chance to win is the simulation's win probability, the same as on the scoreboard.</p>
    </section>
  );
}
