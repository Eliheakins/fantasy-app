import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { sendJson } from "@/api/envelope";
import type { MyLeague } from "@/api/types";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Button } from "@/components/ui/button";
import { useLeague } from "@/lib/league";

const MY_LEAGUES_URL = "/api/me/leagues";
const POLL_MS = 8000;
const STATUS_TEXT: Record<string, string> = {
  queued: "Waiting for the next refresh",
  ready: "Ready",
  error: "Problem",
};

/** The leagues this account added, with where each stands. A new league is read at the next
 * refresh; the list checks every few seconds and tells the rest of the app when one becomes ready. */
export function MyLeagueList() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { setLeague } = useLeague();
  const state = useEnvelopeQuery<MyLeague[]>(MY_LEAGUES_URL, POLL_MS);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const readyBefore = useRef(0);
  const ready = state.kind === "ready" ? state.data.filter((l) => l.status === "ready").length : 0;

  useEffect(() => {
    if (ready > readyBefore.current) void queryClient.invalidateQueries({ queryKey: ["api", "/api/leagues"] });
    readyBefore.current = ready;
  }, [ready, queryClient]);

  async function remove(league: MyLeague) {
    setError(null);
    const sent = await sendJson(`${MY_LEAGUES_URL}/${encodeURIComponent(league.league_id)}`, "DELETE");
    setConfirming(null);
    if (!sent.ok) {
      setError(sent.error.message);
      return;
    }
    await queryClient.invalidateQueries({ queryKey: ["api", MY_LEAGUES_URL] });
    await queryClient.invalidateQueries({ queryKey: ["api", "/api/leagues"] });
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
                  </span>
                  <span className="flex gap-2">
                    {l.status === "ready" && (
                      <Button size="sm" aria-label={`Open ${l.name}`} onClick={() => open(l)}>
                        Open
                      </Button>
                    )}
                    {confirming === l.league_id ? (
                      <>
                        <Button size="sm" onClick={() => void remove(l)}>
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
                </li>
              ))}
            </ul>
          </div>
        )
      }
    </ApiBoundary>
  );
}
