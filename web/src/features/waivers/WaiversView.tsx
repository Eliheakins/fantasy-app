import { useEffect, useRef, useState } from "react";
import type { ApiState } from "@/api/envelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { useApi } from "@/hooks/useApi";
import { useLeague, useLeagueApi } from "@/lib/league";
import { type Who, useWho, whoFor } from "@/features/outlook/who";
import { AddsTable } from "./AddsTable";
import {
  ADDS_CAPTION, ADDS_METHOD, type PlayerWeekRow, STREAM_CAPTION, STREAM_METHOD, STRENGTH_CAPTION, STRENGTH_METHOD,
  type StreamerRow, type StrengthRow, type WaiverRow,
} from "./logic";
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
  who?: Who;
};

const CHART_HINT = "Select a player to see projected points for the next four weeks.";

/** Presentational: all data comes in as props so tests can pass fixture states. */
export function WaiversView({ adds, strength, def, kickers, weeks, selected, onSelect, who = whoFor(null) }: ViewProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const mineMarker = who.name ? "(theirs)" : "(yours)";
  // On a phone the chart sits below the cards, so bring it into view when a player is picked.
  useEffect(() => {
    if (selected !== null) chartRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);
  return (
    <div className="space-y-8">
      <Section title="Adds" caption={ADDS_CAPTION} howCalculated={ADDS_METHOD}>
        <ApiBoundary state={adds}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="py-6 text-muted">No free agent adds expected points for {who.name ?? "your team"}.</p>
            ) : (
              <div className="xl:grid xl:grid-cols-[minmax(0,1fr)_20rem] xl:items-start xl:gap-6">
                <AddsTable rows={rows} selected={selected} onSelect={onSelect} />
                <div ref={chartRef} className="mt-4 xl:sticky xl:top-16 xl:mt-0">
                  {selected === null ? (
                    <p className="card-flat hidden text-caption text-muted xl:block">{CHART_HINT}</p>
                  ) : (
                    <ApiBoundary state={weeks}>
                      {(w) => <PlayerWeeksChart name={rows.find((r) => r.gsis_id === selected)?.full_name ?? ""} weeks={w} />}
                    </ApiBoundary>
                  )}
                </div>
              </div>
            )
          }
        </ApiBoundary>
      </Section>
      <Section title={`Where ${who.name ? `${who.name}'s` : "your"} roster is strong or thin`} caption={STRENGTH_CAPTION} howCalculated={STRENGTH_METHOD}>
        <ApiBoundary state={strength}>{(rows) => <StrengthList rows={rows} />}</ApiBoundary>
      </Section>
      <Section title="Streaming: defense and kicker" caption={STREAM_CAPTION} howCalculated={STREAM_METHOD}>
        <StreamerTable label="Defenses" state={def} mineMarker={mineMarker} />
        <StreamerTable label="Kickers" state={kickers} mineMarker={mineMarker} />
      </Section>
    </div>
  );
}

export function WaiversContent() {
  const { league } = useLeague();
  const who = useWho();
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
      adds={adds} strength={strength} def={def} kickers={kickers} weeks={weeks}
      selected={selected} onSelect={(id) => setSelection({ league, id })} who={who}
    />
  );
}
