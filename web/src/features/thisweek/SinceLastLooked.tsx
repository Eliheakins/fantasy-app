import { useEffect, useRef, useState } from "react";
import type { League } from "@/api/types";
import type { DigestData } from "@/lib/digestTypes";
import { ExplainDelta, NOISE_PERCENT } from "@/viz";
import type { components } from "@/api/schema";
import { isPending } from "@/api/envelope";
import { useAllLeagues, useLeagueQuery } from "@/lib/league";
import { type OddsRun, type Visit, asMs, newAdds, oddsSince, readVisit, writeVisit } from "./visit";
import { leagueName } from "./weekLogic";

type StatusChange = components["schemas"]["StatusChangeRow"];
const MIN_GAP_MS = 30 * 60_000; // a quick reload keeps showing the same changes
const when = (iso: string) =>
  new Date(iso).toLocaleString("en-US", {
    timeZone: "America/New_York",
    timeZoneName: "short",
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
const oddsWhy = (what: string, fromRun: string, toRun: string) =>
  `Change in your ${what} between the saved simulation run of ${when(new Date(asMs(fromRun)).toISOString())} (the last one at or before your last visit) and the latest run, ${when(new Date(asMs(toRun)).toISOString())}. Percentage points.`;
const status = (s: string | null) => s ?? "healthy";

function Changes({
  visit,
  league,
  history,
  changes,
  digest,
}: {
  visit: Visit;
  league: League;
  history: OddsRun[] | null;
  changes: StatusChange[] | null;
  digest: DigestData | null;
}) {
  const odds = history && league.roster_id !== null ? oddsSince(history, league.roster_id, visit.at) : null;
  const added = digest
    ? newAdds(
        digest.waivers.map((w) => w.get),
        visit.adds,
      )
    : [];
  const nothing = !odds && !(changes && changes.length) && added.length === 0;
  return (
    <ul className="list-disc space-y-1 pl-5 text-body">
      {odds && (
        <li>
          Season odds:{" "}
          {odds.playoffs !== null && (
            <>
              <ExplainDelta
                points={odds.playoffs}
                noise={NOISE_PERCENT}
                why={oddsWhy("chance to make the playoffs", odds.fromRun, odds.toRun)}
              >
                {" "}
                playoffs
              </ExplainDelta>
            </>
          )}
          {odds.playoffs !== null && odds.title !== null && ", "}
          {odds.title !== null && (
            <>
              <ExplainDelta points={odds.title} noise={NOISE_PERCENT} why={oddsWhy("title chance", odds.fromRun, odds.toRun)}>
                {" "}
                title
              </ExplainDelta>
            </>
          )}{" "}
          (% points)
        </li>
      )}
      {changes?.map((c) => (
        <li key={c.sleeper_id}>
          {c.full_name ?? c.sleeper_id}: {status(c.before)} to {status(c.after)}
        </li>
      ))}
      {added.length > 0 && <li>New on your waiver list: {added.join(", ")}</li>}
      {nothing && <li className="list-none text-muted">No changes since then.</li>}
    </ul>
  );
}

function LeagueSince({ league }: { league: League }) {
  const key = league.league_key;
  const [visit] = useState(() => readVisit(key)); // read once, before anything is written
  const history = useLeagueQuery(key, visit ? "/api/leagues/{league}/odds-history" : null);
  const changes = useLeagueQuery(key, visit ? "/api/leagues/{league}/status-changes" : null, visit ? { since: visit.at } : undefined);
  const digest = useLeagueQuery(key, "/api/leagues/{league}/digest");
  const written = useRef(false);
  const ready = !isPending(digest) && (visit === null || (!isPending(history) && !isPending(changes)));
  const adds = digest.kind === "ready" ? digest.data.waivers.map((w) => w.get) : (visit?.adds ?? []);
  useEffect(() => {
    if (!ready || written.current) return;
    written.current = true;
    if (visit && Date.now() - Date.parse(visit.at) < MIN_GAP_MS) return;
    writeVisit(key, { at: new Date().toISOString(), adds });
  }); // after the comparison was computed from `visit`, never before
  return (
    <div className="mt-3">
      <h3 className="font-semibold">
        {leagueName(league)}
        {visit && <span className="font-normal text-muted"> since {when(visit.at)}</span>}
      </h3>
      {visit === null ? (
        <p className="text-body text-muted">First visit: we'll show changes from next time.</p>
      ) : (
        <Changes
          visit={visit}
          league={league}
          history={history.kind === "ready" ? history.data : null}
          changes={changes.kind === "ready" ? changes.data : null}
          digest={digest.kind === "ready" ? digest.data : null}
        />
      )}
    </div>
  );
}

/** Per league: what changed since this browser last opened the page (odds, my players' status, new waiver adds). */
export function SinceLastLooked() {
  const leagues = useAllLeagues();
  if (leagues.kind === "error" || leagues.kind === "no_data") {
    return (
      <section aria-labelledby="since-heading" className="mb-6">
        <h2 id="since-heading" className="text-section font-semibold">
          Since you last looked
        </h2>
        <p role="alert" className="text-body text-warning">
          The leagues did not load, so changes cannot be shown.
        </p>
      </section>
    );
  }
  if (leagues.kind !== "ready" || leagues.data.length === 0) return null;
  return (
    <section aria-labelledby="since-heading" className="mb-6">
      <h2 id="since-heading" className="text-section font-semibold">
        Since you last looked
      </h2>
      {leagues.data.map((l) => (
        <LeagueSince key={l.league_key} league={l} />
      ))}
    </section>
  );
}
