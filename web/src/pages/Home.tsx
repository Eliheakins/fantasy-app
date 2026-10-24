import { ApiBoundary } from "@/components/ApiBoundary";
import { LeagueCard } from "@/features/home/LeagueCard";
import { useHomeLeagues } from "@/features/home/hooks";

export default function Home() {
  const leagues = useHomeLeagues();
  return (
    <div className="space-y-4 p-4">
      <h1 className="text-display">Home</h1>
      <ApiBoundary state={leagues}>
        {(list) =>
          list.length === 0 ? (
            <p className="text-muted">No data yet. Run <code>make refresh</code>, then reload this page.</p>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {list.map((l) => <LeagueCard key={l.league_key} league={l} />)}
            </div>
          )
        }
      </ApiBoundary>
    </div>
  );
}
