import { ApiBoundary, NoData } from "@/components/ApiBoundary";
import type { ApiState } from "@/api/envelope";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { formatNumber } from "@/viz";
import { STREAM_PLAYOFF_NOTE, type StreamerRow } from "./logic";

function columns(single: string, mineMarker: string, playoffs: boolean): Column<StreamerRow>[] {
  const base: Column<StreamerRow>[] = [
    { label: single, role: "primary", render: (r) => `${r.name ?? "–"}${r.is_mine ? ` ${mineMarker}` : ""}` },
    { label: "Team", render: (r) => r.team ?? "–" },
    { label: "This week (pts)", numeric: true, render: (r) => formatNumber(r.this_week) },
    { label: "Next 3 weeks (pts)", numeric: true, render: (r) => formatNumber(r.next_three) },
  ];
  return playoffs ? [...base, { label: "Playoff weeks (pts)", numeric: true, render: (r) => formatNumber(r.playoff_points) }] : base;
}

export function StreamerTable({
  label,
  state,
  mineMarker,
  playoffs = false,
}: {
  label: string;
  state: ApiState<StreamerRow[]>;
  mineMarker: string;
  playoffs?: boolean;
}) {
  return (
    <section aria-label={label} className="mt-6 first:mt-0">
      <h3 className="text-body font-semibold">{label}</h3>
      {state.kind === "no_data" ? (
        <NoData message="Run the streaming stage to see this." />
      ) : (
        <ApiBoundary state={state}>
          {(rows) => (
            <div className="max-w-2xl">
              <ResponsiveTable
                caption={label}
                columns={columns(label.slice(0, -1), mineMarker, playoffs)}
                rows={rows}
                rowKey={(r) => `${r.name}-${r.team}`}
                isStrong={(r) => r.is_mine}
              />
              {playoffs && <p className="mt-2 text-caption text-muted">{STREAM_PLAYOFF_NOTE}</p>}
            </div>
          )}
        </ApiBoundary>
      )}
    </section>
  );
}
