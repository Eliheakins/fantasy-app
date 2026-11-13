import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { useLeagueApi } from "@/lib/league";
import { matchText, myBracketStatus, roundHeading } from "./logic";

/** The playoff bracket as text: a heading per round, a list of matches. Hidden until Sleeper has set the bracket. */
export function BracketSection({ myRosterId }: { myRosterId: number | null }) {
  const state = useLeagueApi("/api/leagues/{league}/bracket");
  if (state.kind === "no_data") return null;
  return (
    <Section title="Playoff bracket" caption="Each match's chance to advance comes from the simulation, assuming current rosters.">
      <ApiBoundary state={state}>
        {({ rounds }) => {
          const status = myBracketStatus(rounds, myRosterId);
          return (
            <>
              {status && <p className="mb-3 text-body font-semibold">{status}</p>}
              <div className="grid gap-6 md:grid-cols-2 xl:grid-flow-col xl:auto-cols-fr xl:grid-cols-none">
                {rounds.map((r) => (
                  <div key={r.round} className="min-w-0">
                    <h3 className="text-body font-semibold text-label">{roundHeading(r)}</h3>
                    <ol className="mt-2 space-y-2">
                      {r.matches.map((m) => (
                        <li
                          key={m.m}
                          className={`rounded-lg border border-line bg-surface px-3 py-2 text-body ${m.is_mine ? "mine-row" : ""}`}
                        >
                          {matchText(m, myRosterId)}
                        </li>
                      ))}
                    </ol>
                  </div>
                ))}
              </div>
            </>
          );
        }}
      </ApiBoundary>
    </Section>
  );
}
