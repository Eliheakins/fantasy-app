import { PageHeader } from "@/components/PageHeader";
import { ApiBoundary } from "@/components/ApiBoundary";
import { LeagueCard } from "@/features/home/LeagueCard";
import { useHomeLeagues } from "@/features/home/hooks";
import { asViewedTeam } from "@/features/home/logic";
import { useTeam } from "@/lib/teamContext";

export default function Home() {
  const leagues = useHomeLeagues();
  const { team, league, viewed } = useTeam();
  return (
    <div>
      <PageHeader title="Home" />
      <ApiBoundary state={leagues}>
        {(all) => {
          // roster ids belong to one league: while viewing a team, show only its league
          const list = team === null ? all : all.filter((l) => l.league_key === league);
          return list.length === 0 ? (
            <p className="text-muted">No data yet. Run <code>make refresh</code>, then reload this page.</p>
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">
              {list.map((l) => <LeagueCard key={l.league_key} league={asViewedTeam(l, viewed)} mine={viewed === null} />)}
            </div>
          );
        }}
      </ApiBoundary>
    </div>
  );
}
