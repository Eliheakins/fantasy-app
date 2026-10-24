import { ApiBoundary, NoData } from "@/components/ApiBoundary";
import type { ApiState } from "@/api/envelope";
import { formatNumber } from "@/viz";
import type { StreamerRow } from "./logic";

export function StreamerTable({ label, state }: { label: string; state: ApiState<StreamerRow[]> }) {
  const single = label.slice(0, -1);
  return (
    <section aria-label={label}>
      <h3 className="text-body font-semibold">{label}</h3>
      {state.kind === "no_data" ? (
        <NoData message="Run the streaming stage to see this." />
      ) : (
        <ApiBoundary state={state}>
          {(rows) => (
            <table className="w-full text-body">
              <thead>
                <tr className="text-left text-caption text-muted">
                  <th scope="col">{single}</th>
                  <th scope="col">Team</th>
                  <th scope="col">Mine</th>
                  <th scope="col" className="text-right">This week</th>
                  <th scope="col" className="text-right">Next 3 weeks</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.name}-${r.team}`}>
                    <td>{r.name ?? "–"}</td>
                    <td>{r.team ?? "–"}</td>
                    <td>{r.is_mine ? "Mine" : ""}</td>
                    <td className="text-right tabular-nums">{formatNumber(r.this_week)}</td>
                    <td className="text-right tabular-nums">{formatNumber(r.next_three)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </ApiBoundary>
      )}
    </section>
  );
}
