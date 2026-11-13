import { type FormEvent, useState } from "react";
import type { SleeperLookup } from "@/api/types";
import { useEnvelopeMutation } from "@/api/useEnvelope";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { MY_LEAGUES, MY_LEAGUES_KEY } from "./myLeagues";
import { TeamPicker } from "./TeamPicker";

/** Sleeper's own rule for a username; the server checks it again. */
const USERNAME_PATTERN = "[A-Za-z0-9_]{1,40}";

/** Find a Sleeper user's leagues, then add the ones that are theirs, picking which team in each is
 * yours. The username is not proof of who someone is (Sleeper has no sign-in to check against), so
 * the page says plainly what it does. */
export function AddLeague() {
  const [username, setUsername] = useState("");
  const [lookup, setLookup] = useState<SleeperLookup | null>(null);
  const [picking, setPicking] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const find = useEnvelopeMutation("post", "/api/me/sleeper/lookup");
  const add = useEnvelopeMutation("post", MY_LEAGUES, [MY_LEAGUES_KEY]);
  const adding = add.isPending ? add.variables.body.league_id : null;
  const error = (find.error ?? add.error)?.message ?? null;

  function handleFind(event: FormEvent) {
    event.preventDefault();
    add.reset();
    setAdded(null);
    find.mutate({ body: { username: username.trim() } }, { onSuccess: setLookup, onError: () => setLookup(null) });
  }

  function handleAdd(leagueId: string, name: string, rosterId: number) {
    const body = { username: username.trim(), league_id: leagueId, roster_id: rosterId };
    add.mutate(
      { body },
      {
        onSuccess: () => {
          setPicking(null);
          setAdded(name);
          setLookup((current) =>
            current ? { ...current, leagues: current.leagues.map((l) => (l.league_id === leagueId ? { ...l, added: true } : l)) } : current,
          );
        },
      },
    );
  }

  return (
    <div>
      <form onSubmit={handleFind} className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <Field
          id="sleeper-username"
          label="Your Sleeper username"
          wrapperClassName="flex-1"
          required
          pattern={USERNAME_PATTERN}
          autoComplete="off"
          autoCapitalize="none"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <Button type="submit" disabled={find.isPending}>
          {find.isPending ? "Looking…" : "Find my leagues"}
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
                      onConfirm={(rosterId) => handleAdd(l.league_id, l.name, rosterId)}
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
