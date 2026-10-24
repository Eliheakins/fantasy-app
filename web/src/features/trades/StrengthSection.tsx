import { ApiBoundary } from "@/components/ApiBoundary";
import { useLeagueApi } from "@/lib/league";
import type { Strength } from "./types";

export function StrengthSection() {
  const state = useLeagueApi<Strength[]>("strength");
  return (
    <section aria-labelledby="strength-h" className="space-y-2">
      <h2 id="strength-h" className="text-body font-semibold">Where your roster is strong or thin</h2>
      <ApiBoundary state={state}>
        {(rows) => (
          <table className="w-full max-w-xl tabular-nums">
            <thead>
              <tr className="text-left text-caption text-muted">
                <th scope="col" className="py-1 font-normal">Position</th>
                <th scope="col" className="py-1 text-right font-normal">Points a week over replacement</th>
                <th scope="col" className="py-1 text-right font-normal">League rank</th>
                <th scope="col" className="py-1 text-right font-normal">Teams</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.position} className="border-t border-border">
                  <th scope="row" className="py-1 text-left font-normal">{r.position}</th>
                  <td className="py-1 text-right">{r.vor_per_week.toFixed(1)}</td>
                  <td className="py-1 text-right">{r.rank}</td>
                  <td className="py-1 text-right">{r.teams}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </ApiBoundary>
      <p className="text-caption text-muted">
        Deep positions (rank near 1) are where a trade can come from; thin ones are the needs.
      </p>
    </section>
  );
}
