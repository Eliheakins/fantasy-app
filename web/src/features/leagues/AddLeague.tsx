import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { sendJson } from "@/api/envelope";
import type { MyLeague, SleeperLookup } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TeamPicker } from "./TeamPicker";

const MY_LEAGUES_KEY = ["api", "/api/me/leagues"] as const;
/** Sleeper's own rule for a username; the server checks it again. */
const USERNAME_PATTERN = "[A-Za-z0-9_]{1,40}";

type Props = { username: string; onUsername: (name: string) => void };

/** Find a Sleeper user's leagues, then add the ones that are theirs, picking which team in each is
 * yours. The username is not proof of who someone is (Sleeper has no sign-in to check against), so
 * the page says plainly what it does. */
export function AddLeague({ username, onUsername }: Props) {
  const queryClient = useQueryClient();
  const [lookup, setLookup] = useState<SleeperLookup | null>(null);
  const [looking, setLooking] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const [picking, setPicking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);

  async function handleFind(event: FormEvent) {
    event.preventDefault();
    setLooking(true);
    setError(null);
    setAdded(null);
    const sent = await sendJson<SleeperLookup>("/api/me/sleeper/lookup", "POST", { username: username.trim() });
    setLooking(false);
    if (!sent.ok) {
      setLookup(null);
      setError(sent.error.message);
      return;
    }
    setLookup(sent.data);
  }

  async function handleAdd(leagueId: string, name: string, rosterId: number) {
    setAdding(leagueId);
    setError(null);
    const body = { username: username.trim(), league_id: leagueId, roster_id: rosterId };
    const sent = await sendJson<MyLeague>("/api/me/leagues", "POST", body);
    setAdding(null);
    if (!sent.ok) {
      setError(sent.error.message);
      return;
    }
    setPicking(null);
    setAdded(name);
    setLookup((current) =>
      current ? { ...current, leagues: current.leagues.map((l) => (l.league_id === leagueId ? { ...l, added: true } : l)) } : current,
    );
    await queryClient.invalidateQueries({ queryKey: MY_LEAGUES_KEY });
  }

  return (
    <div>
      <form onSubmit={(e) => void handleFind(e)} className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="flex flex-1 flex-col gap-1">
          <label htmlFor="sleeper-username" className="text-body font-medium text-ink">
            Your Sleeper username
          </label>
          <Input
            id="sleeper-username"
            required
            pattern={USERNAME_PATTERN}
            autoComplete="off"
            autoCapitalize="none"
            value={username}
            onChange={(e) => onUsername(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={looking}>
          {looking ? "Looking…" : "Find my leagues"}
        </Button>
      </form>
      <p className="mt-2 max-w-prose text-caption text-muted">
        Use your own username. Sleeper cannot confirm who you are, but a league is only added if one of its teams is yours.
      </p>
      {error && (
        <p role="alert" className="mt-3 text-body text-ink">
          {error}
        </p>
      )}
      {added && (
        <p role="status" className="mt-3 text-body text-ink">
          Added {added}. It will be ready after the next refresh, usually within a few minutes.
        </p>
      )}
      {lookup && (
        <div className="mt-4">
          <h3 className="text-body font-semibold text-ink">Leagues for {lookup.display_name} this season</h3>
          {lookup.leagues.length === 0 ? (
            <p className="mt-2 text-body text-muted">No leagues found for this season.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line border-y border-line">
              {lookup.leagues.map((l) => (
                <li key={l.league_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span>
                    <span className="text-body text-ink">{l.name}</span>
                    {l.num_teams !== null && <span className="ml-2 text-caption text-muted">{l.num_teams} teams</span>}
                    {l.problem && <span className="block text-caption text-muted">Cannot be added: {l.problem}</span>}
                  </span>
                  {l.added ? (
                    <span className="text-caption text-label">Added</span>
                  ) : (
                    picking !== l.league_id && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={l.problem !== null || adding !== null}
                        aria-label={`Add ${l.name}`}
                        onClick={() => setPicking(l.league_id)}
                      >
                        Add
                      </Button>
                    )
                  )}
                  {picking === l.league_id && !l.added && (
                    <TeamPicker
                      leagueId={l.league_id}
                      leagueName={l.name}
                      initial={null}
                      ownerId={lookup.user_id}
                      confirmLabel={`Add ${l.name}`}
                      isBusy={adding === l.league_id}
                      onConfirm={(rosterId) => void handleAdd(l.league_id, l.name, rosterId)}
                      onCancel={() => setPicking(null)}
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
