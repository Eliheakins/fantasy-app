import { type QueryKey, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { MyLeague } from "@/api/types";
import { apiKey, useEnvelopeMutation, useEnvelopeQuery } from "@/api/useEnvelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Button } from "@/components/ui/button";
import { useLeague } from "@/lib/league";
import { MY_LEAGUES, MY_LEAGUES_KEY } from "./myLeagues";
import { TeamPicker } from "./TeamPicker";

const POLL_MS = 8000;
const LEAGUES_KEY = apiKey("/api/leagues");
const STATUS_TEXT: Record<string, string> = {
  queued: "Waiting for the next refresh",
  ready: "Ready",
  error: "Problem",
};

/** The leagues this account added, with where each stands and a way to change which team is yours.
 * A league added before teams were picked asks for one. A new league is read at the next refresh;
 * the list checks every few seconds and tells the rest of the app when one becomes ready. */
export function MyLeagueList() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { setLeague } = useLeague();
  const state = useEnvelopeQuery(MY_LEAGUES, {}, POLL_MS);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [picking, setPicking] = useState<string | null>(null);
  // No hook-level invalidation: the confirm and picker close when the write returns, and the refetch runs behind them.
  const removing = useEnvelopeMutation("delete", "/api/me/leagues/{league_id}");
  const changing = useEnvelopeMutation("put", "/api/me/leagues/{league_id}/team");
  const refetch = (...keys: readonly QueryKey[]) => {
    for (const queryKey of keys) void queryClient.invalidateQueries({ queryKey });
  };
  const error = (removing.error ?? changing.error)?.message ?? null;
  // null until the list first loads, so a visit does not refetch /api/leagues for leagues already ready.
  const readyBefore = useRef<number | null>(null);
  const ready = state.kind === "ready" ? state.data.filter((l) => l.status === "ready").length : null;

  useEffect(() => {
    if (ready === null) return;
    if (readyBefore.current !== null && ready > readyBefore.current) void queryClient.invalidateQueries({ queryKey: LEAGUES_KEY });
    readyBefore.current = ready;
  }, [ready, queryClient]);

  function remove(league: MyLeague) {
    changing.reset();
    removing.mutate(
      { params: { path: { league_id: league.league_id } } },
      { onSettled: () => setConfirming(null), onSuccess: () => refetch(MY_LEAGUES_KEY, LEAGUES_KEY) },
    );
  }

  function changeTeam(league: MyLeague, rosterId: number) {
    removing.reset();
    changing.mutate(
      { params: { path: { league_id: league.league_id } }, body: { roster_id: rosterId } },
      {
        onSuccess: () => {
          setPicking(null);
          refetch(["api"]); // every page that shows "your team"
        },
      },
    );
  }

  function open(league: MyLeague) {
    setLeague(league.league_key);
    navigate("/");
  }

  return (
    <ApiBoundary state={state}>
      {(leagues) =>
        leagues.length === 0 ? (
          <p className="text-body text-muted">You have not added a league yet.</p>
        ) : (
          <div>
            {error && (
              <p role="alert" className="mb-3 text-body text-ink">
                {error}
              </p>
            )}
            <ul className="divide-y divide-line border-y border-line">
              {leagues.map((l) => (
                <li key={l.league_id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                  <span>
                    <span className="text-body font-medium text-ink">{l.name}</span>
                    <span className="block text-caption text-muted">
                      {STATUS_TEXT[l.status] ?? l.status}
                      {l.error ? `: ${l.error}` : ""}
                    </span>
                    {l.roster_id === null && (
                      <span className="block text-caption text-ink">
                        No team picked yet. Pick yours to confirm which team the app shows as you.
                      </span>
                    )}
                  </span>
                  <span className="flex flex-wrap gap-2">
                    {picking !== l.league_id && (
                      <Button
                        size="sm"
                        variant={l.roster_id === null ? "default" : "outline"}
                        aria-label={`${l.roster_id === null ? "Pick" : "Change"} your team in ${l.name}`}
                        onClick={() => setPicking(l.league_id)}
                      >
                        {l.roster_id === null ? "Pick your team" : "Change team"}
                      </Button>
                    )}
                    {l.status === "ready" && (
                      <Button size="sm" aria-label={`Open ${l.name}`} onClick={() => open(l)}>
                        Open
                      </Button>
                    )}
                    {confirming === l.league_id ? (
                      <>
                        <Button size="sm" onClick={() => remove(l)}>
                          Confirm remove {l.name}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setConfirming(null)}>
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <Button size="sm" variant="ghost" onClick={() => setConfirming(l.league_id)}>
                        Remove {l.name}
                      </Button>
                    )}
                  </span>
                  {picking === l.league_id && (
                    <TeamPicker
                      leagueId={l.league_id}
                      leagueName={l.name}
                      initial={l.roster_id}
                      confirmLabel="Save team"
                      isBusy={changing.isPending}
                      onConfirm={(rosterId) => changeTeam(l, rosterId)}
                      onCancel={() => setPicking(null)}
                    />
                  )}
                </li>
              ))}
            </ul>
          </div>
        )
      }
    </ApiBoundary>
  );
}
