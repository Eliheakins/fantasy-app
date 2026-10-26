import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { barFraction, ordinal } from "@/features/league/logic";
import { HBar } from "@/features/league/PowerRankings";
import { useLeagueApi } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";
import type { Strength } from "./types";

const POSITION_ORDER = ["QB", "RB", "WR", "TE"];
const orderOf = (position: string) => {
  const i = POSITION_ORDER.indexOf(position);
  return i === -1 ? POSITION_ORDER.length : i;
};

export function StrengthSection() {
  const state = useLeagueApi<Strength[]>("strength");
  const { viewed } = useTeam();
  const owner = viewed ? `${viewed.team_name}'s` : "your";
  return (
    <Section
      title={`Where ${owner} roster is strong or thin`}
      caption="A low rank is a deep position, where a trade can come from. A high rank is thin: that is the need."
    >
      <ApiBoundary state={state}>
        {(rows) => {
          const sorted = [...rows].sort((a, b) => orderOf(a.position) - orderOf(b.position));
          const max = Math.max(0, ...sorted.map((r) => r.vor_per_week));
          return (
            <table className="w-full max-w-xl tabular-nums">
              <caption className="sr-only">Strength by position</caption>
              <thead>
                <tr className="text-left text-caption text-muted">
                  <th scope="col" className="py-1 font-normal">Position</th>
                  <th scope="col" className="py-1 font-normal">Points a week over a free agent</th>
                  <th scope="col" className="py-1 text-right font-normal">League rank</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => (
                  <tr key={r.position} className="border-t border-border">
                    <th scope="row" className="py-1 text-left font-normal">{r.position}</th>
                    <td className="py-1">
                      <span className="flex items-center gap-2">
                        <span className="w-10 text-right">{r.vor_per_week.toFixed(1)}</span>
                        <span className="w-16 sm:w-32">
                          <HBar fraction={barFraction(r.vor_per_week, max)} label={`${r.vor_per_week.toFixed(1)} points a week`} />
                        </span>
                      </span>
                    </td>
                    <td className="py-1 text-right whitespace-nowrap">{`${ordinal(r.rank)} of ${r.teams}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          );
        }}
      </ApiBoundary>
    </Section>
  );
}
