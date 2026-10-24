import { useState } from "react";
import type { ApiState } from "@/api/envelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { useApi } from "@/hooks/useApi";
import { useLeague, useLeagueApi } from "@/lib/league";
import { AddsTable } from "./AddsTable";
import { ADDS_CAPTION, type PlayerWeekRow, STREAM_CAPTION, TRENDING_CAPTION, type StreamerRow, type StrengthRow, type WaiverRow } from "./logic";
import { PlayerWeeksChart } from "./PlayerWeeksChart";
import { StreamerTable } from "./StreamerTable";
import { StrengthList } from "./StrengthList";

type ViewProps = {
  adds: ApiState<WaiverRow[]>;
  strength: ApiState<StrengthRow[]>;
  def: ApiState<StreamerRow[]>;
  kickers: ApiState<StreamerRow[]>;
  weeks: ApiState<PlayerWeekRow[]>;
  selected: string | null;
  onSelect: (gsisId: string) => void;
};

/** Presentational: all data comes in as props so tests can pass fixture states. */
export function WaiversView({ adds, strength, def, kickers, weeks, selected, onSelect }: ViewProps) {
  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-body font-semibold">Adds</h2>
        <ApiBoundary state={adds}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="py-6 text-muted">No free agent adds expected points to your team.</p>
            ) : (
              <>
                <p className="mb-2 text-caption text-muted">{ADDS_CAPTION}</p>
                <AddsTable rows={rows} selected={selected} onSelect={onSelect} />
                <p className="mt-2 text-caption text-muted">{TRENDING_CAPTION}</p>
                {selected !== null && (
                  <ApiBoundary state={weeks}>
                    {(w) => (
                      <PlayerWeeksChart
                        name={rows.find((r) => r.gsis_id === selected)?.full_name ?? ""}
                        weeks={w}
                      />
                    )}
                  </ApiBoundary>
                )}
              </>
            )
          }
        </ApiBoundary>
      </section>
      <section>
        <h2 className="text-body font-semibold">Where your roster is strong or thin</h2>
        <ApiBoundary state={strength}>{(rows) => <StrengthList rows={rows} />}</ApiBoundary>
      </section>
      <section>
        <h2 className="text-body font-semibold">Streaming: defense and kicker</h2>
        <p className="mb-2 text-caption text-muted">{STREAM_CAPTION}</p>
        <StreamerTable label="Defenses" state={def} />
        <StreamerTable label="Kickers" state={kickers} />
      </section>
    </div>
  );
}

export function WaiversContent() {
  const { league } = useLeague();
  const [selection, setSelection] = useState<{ league: string | null; id: string } | null>(null);
  // A pick belongs to the league it was made in.
  const selected = selection && selection.league === league ? selection.id : null;
  const adds = useLeagueApi<WaiverRow[]>("waivers");
  const strength = useLeagueApi<StrengthRow[]>("strength");
  const def = useLeagueApi<StreamerRow[]>("streamers?kind=DEF");
  const kickers = useLeagueApi<StreamerRow[]>("streamers?kind=K");
  const weeks = useApi<PlayerWeekRow[]>(
    league && selected
      ? `/api/leagues/${encodeURIComponent(league)}/player-weeks?gsis_id=${encodeURIComponent(selected)}&n=4`
      : null,
  );
  return (
    <WaiversView
      adds={adds}
      strength={strength}
      def={def}
      kickers={kickers}
      weeks={weeks}
      selected={selected}
      onSelect={(id) => setSelection({ league, id })}
    />
  );
}
