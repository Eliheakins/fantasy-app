import { useEffect, useRef, useState } from "react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { ApiState } from "@/api/envelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { ExternalLink } from "@/components/ExternalLink";
import { sleeperLeagueUrl } from "@/lib/sleeper";
import { useLeague, useLeagueApi, useLeagueRow } from "@/lib/league";
import { type Who, useWho, whoFor } from "@/lib/who";
import { AddsTable } from "./AddsTable";
import {
  ADDS_CAPTION,
  ADDS_CAPTION_PLAYOFFS,
  ADDS_METHOD,
  type PlayerWeekRow,
  type PlayoffWeeks,
  isStreamPos,
  noAddsText,
  type Pos,
  playoffLabel,
  playoffWeeksOf,
  type Rank,
  STREAM_CAPTION,
  STREAMING_ANCHOR,
  STREAM_METHOD,
  type StashData,
  type StreamerRow,
  type WaiverRow,
} from "./logic";
import { PlayerWeeksChart } from "./PlayerWeeksChart";
import { OpenIrCallout, StashSection } from "./StashSection";
import { StreamerTable } from "./StreamerTable";
import { linkButtonClass } from "@/components/ui/styles";
import { cn } from "@/lib/utils";

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
  /** Show only this position's adds (`?pos=`). */
  pos?: Pos | null;
  onShowAll?: () => void;
};

const RANKS: { value: Rank; label: string }[] = [
  { value: "ros", label: "Rest of season" },
  { value: "playoffs", label: "Playoff weeks" },
];

const CHART_HINT = "Select a player to see projected points for the next four weeks.";

type AddsProps = Omit<Required<ViewProps>, "def" | "kickers" | "stash">;

/** The ranked adds with the rank toggle, the position filter and the selected player's chart. */
function AddsSection({ adds, weeks, selected, onSelect, who, sleeperLeagueId, rank, onRank, playoffWeeks, pos, onShowAll }: AddsProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  // On a phone the chart sits below the cards, so bring it into view when a player is picked.
  useEffect(() => {
    if (selected !== null) chartRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);
  const mode = rank === "playoffs" ? playoffLabel(playoffWeeks) : "rest of season";
  const count = adds.kind === "ready" ? `, ${adds.data.length} adds` : "";
  return (
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
      {pos !== null && (
        <p className="mb-3 text-body">
          Showing {pos} only,{" "}
          <button type="button" onClick={onShowAll} className="min-h-[44px] underline underline-offset-2 lg:min-h-0">
            Show all
          </button>
        </p>
      )}
      {sleeperLeagueId && <ExternalLink href={sleeperLeagueUrl(sleeperLeagueId)}>Open league in Sleeper</ExternalLink>}
      <ApiBoundary state={adds}>
        {(all) => {
          const rows = pos === null ? all : all.filter((r) => r.position === pos); // K and DEF are never adds
          const streamPos = pos !== null && isStreamPos(pos);
          return rows.length === 0 ? (
            <p className="py-6 text-muted">
              {noAddsText(pos, who.name)}
              {streamPos && (
                <a href={`#${STREAMING_ANCHOR}`} className={cn(linkButtonClass, "underline-offset-2 lg:min-h-0")}>
                  See streaming picks
                </a>
              )}
            </p>
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
          );
        }}
      </ApiBoundary>
    </Section>
  );
}

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
  pos = null,
  onShowAll = () => {},
}: ViewProps) {
  const mineMarker = who.name ? "(theirs)" : "(yours)";
  return (
    <div className="space-y-8">
      {stash.kind === "ready" && <OpenIrCallout data={stash.data} />}
      <AddsSection
        adds={adds}
        weeks={weeks}
        selected={selected}
        onSelect={onSelect}
        who={who}
        sleeperLeagueId={sleeperLeagueId}
        rank={rank}
        onRank={onRank}
        playoffWeeks={playoffWeeks}
        pos={pos}
        onShowAll={onShowAll}
      />
      <StashSection state={stash} />
      <div id={STREAMING_ANCHOR}>
        <Section title="Streaming: defense and kicker" caption={STREAM_CAPTION} howCalculated={STREAM_METHOD}>
          <StreamerTable label="Defenses" state={def} mineMarker={mineMarker} playoffs={rank === "playoffs"} />
          <StreamerTable label="Kickers" state={kickers} mineMarker={mineMarker} playoffs={rank === "playoffs"} />
        </Section>
      </div>
    </div>
  );
}

/** The adds ranking and position filter, which the Moves page keeps in its URL (`?rank=`, `?pos=`). */
export type WaiverParams = { rank: Rank; onRank: (next: Rank) => void; pos: Pos | null; onShowAll: () => void };

export function WaiversContent({ rank, onRank, pos, onShowAll }: WaiverParams) {
  const { league } = useLeague();
  const row = useLeagueRow();
  const sleeperLeagueId = row?.league_id || null;
  const who = useWho();
  const [selection, setSelection] = useState<{ league: string | null; id: string } | null>(null);
  // A pick belongs to the league it was made in.
  const selected = selection && selection.league === league ? selection.id : null;
  const playoffWeeks = playoffWeeksOf(row);
  const adds = useLeagueApi("/api/leagues/{league}/waivers", rank === "playoffs" ? { horizon: "playoffs" } : undefined);
  const def = useLeagueApi("/api/leagues/{league}/streamers", { kind: "DEF" });
  const kickers = useLeagueApi("/api/leagues/{league}/streamers", { kind: "K" });
  const stash = useLeagueApi("/api/leagues/{league}/stash");
  const weeks = useEnvelopeQuery(
    "/api/leagues/{league}/player-weeks",
    league && selected ? { path: { league }, query: { gsis_id: selected, n: 4 } } : null,
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
      onRank={onRank}
      playoffWeeks={playoffWeeks}
      pos={pos}
      onShowAll={onShowAll}
    />
  );
}
