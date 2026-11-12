import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { ApiState } from "@/api/envelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { ExternalLink } from "@/components/ExternalLink";
import { sleeperLeagueUrl } from "@/lib/sleeper";
import { useLeague, useLeagueApi } from "@/lib/league";
import { type Who, useWho, whoFor } from "@/lib/who";
import { AddsTable } from "./AddsTable";
import {
  ADDS_CAPTION,
  ADDS_CAPTION_PLAYOFFS,
  ADDS_METHOD,
  type PlayerWeekRow,
  type PlayoffWeeks,
  playoffLabel,
  type Rank,
  STREAM_CAPTION,
  STREAM_METHOD,
  type StashData,
  type StreamerRow,
  type WaiverRow,
} from "./logic";
import { PlayerWeeksChart } from "./PlayerWeeksChart";
import { OpenIrCallout, StashSection } from "./StashSection";
import { StreamerTable } from "./StreamerTable";

type ViewProps = {
  adds: ApiState<WaiverRow[]>;
  def: ApiState<StreamerRow[]>;
  kickers: ApiState<StreamerRow[]>;
  weeks: ApiState<PlayerWeekRow[]>;
  stash: ApiState<StashData>;
  selected: string | null;
  onSelect: (gsisId: string) => void;
  who?: Who;
  /** The selected league's Sleeper id; no link when null. */
  sleeperLeagueId?: string | null;
  rank?: Rank;
  onRank?: (rank: Rank) => void;
  playoffWeeks?: PlayoffWeeks;
};

const RANKS: { value: Rank; label: string }[] = [
  { value: "ros", label: "Rest of season" },
  { value: "playoffs", label: "Playoff weeks" },
];

const CHART_HINT = "Select a player to see projected points for the next four weeks.";

/** Presentational: all data comes in as props so tests can pass fixture states. */
export function WaiversView({
  adds,
  def,
  kickers,
  weeks,
  stash,
  selected,
  onSelect,
  who = whoFor(null),
  sleeperLeagueId = null,
  rank = "ros",
  onRank = () => {},
  playoffWeeks = null,
}: ViewProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const mineMarker = who.name ? "(theirs)" : "(yours)";
  // On a phone the chart sits below the cards, so bring it into view when a player is picked.
  useEffect(() => {
    if (selected !== null) chartRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);
  const mode = rank === "playoffs" ? playoffLabel(playoffWeeks) : "rest of season";
  const count = adds.kind === "ready" ? `, ${adds.data.length} adds` : "";
  return (
    <div className="space-y-8">
      {stash.kind === "ready" && <OpenIrCallout data={stash.data} />}
      <Section title="Adds" caption={rank === "playoffs" ? ADDS_CAPTION_PLAYOFFS : ADDS_CAPTION} howCalculated={ADDS_METHOD}>
        <ToggleGroup
          type="single"
          aria-label="Rank adds by"
          value={rank}
          onValueChange={(v) => v && onRank(v as Rank)}
          className="mb-3 w-full justify-start [&>*]:flex-1 md:w-auto md:[&>*]:flex-none"
        >
          {RANKS.map((r) => (
            <ToggleGroupItem key={r.value} value={r.value}>
              {r.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <p role="status" className="sr-only">{`Ranked by ${mode}${count}`}</p>
        {sleeperLeagueId && <ExternalLink href={sleeperLeagueUrl(sleeperLeagueId)}>Open league in Sleeper</ExternalLink>}
        <ApiBoundary state={adds}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="py-6 text-muted">No free agent adds expected points for {who.name ?? "your team"}.</p>
            ) : (
              <div className="xl:grid xl:grid-cols-[minmax(0,1fr)_20rem] xl:items-start xl:gap-6">
                <AddsTable rows={rows} selected={selected} onSelect={onSelect} />
                <div ref={chartRef} className="mt-4 xl:sticky xl:top-[calc(var(--chrome-h)+1rem)] xl:mt-0">
                  {selected === null ? (
                    <p className="hidden text-caption text-muted xl:block">{CHART_HINT}</p>
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
      <StashSection state={stash} />
      <Section title="Streaming: defense and kicker" caption={STREAM_CAPTION} howCalculated={STREAM_METHOD}>
        <StreamerTable label="Defenses" state={def} mineMarker={mineMarker} playoffs={rank === "playoffs"} />
        <StreamerTable label="Kickers" state={kickers} mineMarker={mineMarker} playoffs={rank === "playoffs"} />
      </Section>
    </div>
  );
}

export function WaiversContent() {
  const { league, leagues } = useLeague();
  const sleeperLeagueId = (leagues.kind === "ready" && leagues.data.find((l) => l.league_key === league)?.league_id) || null;
  const who = useWho();
  const [selection, setSelection] = useState<{ league: string | null; id: string } | null>(null);
  // A pick belongs to the league it was made in.
  const selected = selection && selection.league === league ? selection.id : null;
  const [params, setParams] = useSearchParams();
  const rank: Rank = params.get("rank") === "playoffs" ? "playoffs" : "ros";
  const setRank = useCallback(
    (next: Rank) =>
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev);
          if (next === "ros") out.delete("rank");
          else out.set("rank", next);
          return out;
        },
        { replace: true },
      ),
    [setParams],
  );
  const row = leagues.kind === "ready" ? leagues.data.find((l) => l.league_key === league) : undefined;
  const playoffWeeks: PlayoffWeeks =
    row?.playoff_week_start != null && row.playoff_weeks
      ? { first: row.playoff_week_start, last: row.playoff_week_start + row.playoff_weeks - 1 }
      : null;
  const adds = useLeagueApi<WaiverRow[]>(rank === "playoffs" ? "waivers?horizon=playoffs" : "waivers");
  const def = useLeagueApi<StreamerRow[]>("streamers?kind=DEF");
  const kickers = useLeagueApi<StreamerRow[]>("streamers?kind=K");
  const stash = useLeagueApi<StashData>("stash");
  const weeks = useEnvelopeQuery<PlayerWeekRow[]>(
    league && selected ? `/api/leagues/${encodeURIComponent(league)}/player-weeks?gsis_id=${encodeURIComponent(selected)}&n=4` : null,
  );
  return (
    <WaiversView
      adds={adds}
      def={def}
      kickers={kickers}
      weeks={weeks}
      stash={stash}
      selected={selected}
      onSelect={(id) => setSelection({ league, id })}
      who={who}
      sleeperLeagueId={sleeperLeagueId}
      rank={rank}
      onRank={setRank}
      playoffWeeks={playoffWeeks}
    />
  );
}
