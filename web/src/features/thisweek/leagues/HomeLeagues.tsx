import { ApiBoundary } from "@/components/ApiBoundary";
import { LeagueCard } from "./LeagueCard";
import { useAllLeagues } from "@/lib/league";
import { asViewedTeam } from "./logic";
import { useTeam } from "@/lib/teamContext";

/** One card per league (the viewed team's league only while viewing another team). */
export function HomeLeagues() {
  const leagues = useAllLeagues();
  const { team, league, viewed } = useTeam();
  return (
    <div>
      <ApiBoundary state={leagues}>
        {(all) => {
          // roster ids belong to one league: while viewing a team, show only its league
          const list = team === null ? all : all.filter((l) => l.league_key === league);
          return list.length === 0 ? (
            <p className="text-muted">
              No data yet. Run <code>make refresh</code>, then reload this page.
            </p>
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">
              {list.map((l) => (
                <LeagueCard key={l.league_key} league={asViewedTeam(l, viewed)} mine={viewed === null} />
              ))}
            </div>
          );
        }}
      </ApiBoundary>
    </div>
  );
}
