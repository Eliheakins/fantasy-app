import { AddChipTrigger, BarChip, RemovableChip } from "@/features/explore/BarChip";
import { FilterPopover } from "@/features/explore/FilterPopover";
import { LeagueFilterControl } from "@/features/explore/LeagueFilterControl";
import { MinPlaysSlider } from "@/features/explore/MinPlaysSlider";
import { PlayerSearch, type PlayerSearchProps } from "@/features/explore/PlayerSearch";
import { RankingControl } from "@/features/explore/RankingControl";
import { SplitControl } from "@/features/explore/SplitControl";
import { StatPicker } from "@/features/explore/StatPicker";
import { TeamPicker } from "@/features/explore/TeamPicker";
import { useLeagueOwners } from "@/features/explore/useLeagueOwners";
import { usePinnedPlayers } from "@/features/explore/usePinnedPlayers";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useLeagueName } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";
import { getStatById } from "@/stat/config/statDictionary";
import { TEAMS } from "@/stat/config/teams";
import { statLabel } from "@/stat/lib/queryBuilder";
import type { GranularityMode } from "@/stat/types/queryBuilder";
import type { Position, RosterFilter } from "@/stat/lib/queryUrl";
import { useFilterChipGroups } from "@/stat/react/filterChipGroups";
import { useQueryState } from "@/stat/react/useQueryState";

const GRANULARITY_LABELS: Record<GranularityMode, string> = { total: "Total", per_game: "Per game", per_play: "Per play" };
const POSITIONS: readonly Position[] = ["QB", "RB", "WR", "TE"];
const ALL = "all";
const TOGGLE = "rounded-md";

function SubjectChip({ playerSearch }: { playerSearch: PlayerSearchProps }) {
  const { state, setSubject } = useQueryState();
  return (
    <BarChip ariaLabel="Players or teams" label={state.subject === "teams" ? "Teams" : "Players"}>
      <div className="space-y-3">
        <ToggleGroup
          type="single"
          value={state.subject}
          onValueChange={(v) => (v === "players" || v === "teams") && setSubject(v)}
          className="flex gap-2"
          aria-label="Players or teams"
        >
          <ToggleGroupItem value="players" className={TOGGLE}>
            Players
          </ToggleGroupItem>
          <ToggleGroupItem value="teams" className={TOGGLE}>
            Teams
          </ToggleGroupItem>
        </ToggleGroup>
        {state.subject === "teams" ? <TeamPicker /> : <PlayerSearch {...playerSearch} />}
      </div>
    </BarChip>
  );
}

function GranularityChip() {
  const { state, setActiveGranularity } = useQueryState();
  const rateLocked = state.stats.some((id) => getStatById(id)?.rate_only);
  return (
    <BarChip ariaLabel="Total, per game or per play" label={GRANULARITY_LABELS[state.granularity]}>
      <div className="space-y-2">
        <ToggleGroup
          type="single"
          value={state.granularity}
          onValueChange={(v) => v && setActiveGranularity(v as GranularityMode)}
          className="flex flex-wrap gap-2"
          aria-label="Total, per game or per play"
        >
          {(Object.keys(GRANULARITY_LABELS) as GranularityMode[]).map((g) => (
            <ToggleGroupItem key={g} value={g} disabled={rateLocked && g !== "per_play"} className={TOGGLE}>
              {GRANULARITY_LABELS[g]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <p className="text-caption text-muted">
          Per game divides by games played. {rateLocked ? "A rate stat you chose can only be shown per play." : ""}
        </p>
      </div>
    </BarChip>
  );
}

function SeasonChip() {
  const { filterChipState, applyFilterGroup } = useQueryState();
  const group = useFilterChipGroups().find((g) => g.id === "season");
  if (!group) return null;
  const ids = group.options.map((o) => o.id);
  const on = group.options.filter((o) => filterChipState[o.id]);
  const label = on.length === 0 ? "All seasons" : on.length <= 2 ? on.map((o) => o.label).join(", ") : `${on.length} seasons`;
  return (
    <BarChip ariaLabel="Seasons" label={label}>
      <ToggleGroup
        type="multiple"
        value={on.map((o) => o.id)}
        onValueChange={(next) => applyFilterGroup(ids, next)}
        className="flex flex-wrap gap-2"
        aria-label="Seasons"
      >
        {group.options.map((o) => (
          <ToggleGroupItem key={o.id} value={o.id} className={TOGGLE}>
            {o.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </BarChip>
  );
}

function PositionChip() {
  const { state, setPosition } = useQueryState();
  if (state.subject === "teams") return null;
  return (
    <BarChip ariaLabel="Position" label={state.position ?? "All positions"}>
      <ToggleGroup
        type="single"
        value={state.position ?? ALL}
        onValueChange={(v) => v && setPosition(v === ALL ? null : (v as Position))}
        className="flex flex-wrap gap-2"
        aria-label="Position"
      >
        <ToggleGroupItem value={ALL} className={TOGGLE}>
          All positions
        </ToggleGroupItem>
        {POSITIONS.map((p) => (
          <ToggleGroupItem key={p} value={p} className={TOGGLE}>
            {p}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </BarChip>
  );
}

function LeagueChip() {
  const { state } = useQueryState();
  const { league } = useLeagueOwners();
  const { viewed } = useTeam();
  if (league === null || state.subject === "teams") return null;
  const names: Record<RosterFilter, string> = { mine: viewed?.team_name ?? "My roster", rostered: "Rostered", fa: "Free agents" };
  return (
    <BarChip ariaLabel="League" label={state.roster ? names[state.roster] : "All players"}>
      <LeagueFilterControl />
    </BarChip>
  );
}

function RankingChip() {
  const { state } = useQueryState();
  const leagueName = useLeagueName();
  const ranked = state.order ? getStatById(state.order.metric) : undefined;
  const label =
    ranked && state.limit !== null
      ? `${state.order?.direction === "asc" ? "Bottom" : "Top"} ${state.limit} by ${statLabel(ranked, leagueName)}`
      : "No ranking";
  return (
    <BarChip ariaLabel="Ranking and options" label={label}>
      <div className="space-y-5">
        <RankingControl />
        <MinPlaysSlider embedded />
        <SplitControl />
      </div>
    </BarChip>
  );
}

/** Situation filters that are on, as chips you can remove (season has its own chip). */
function ActiveFilterChips() {
  const { state, toggleFilterId } = useQueryState();
  const groups = useFilterChipGroups();
  return state.filters.flatMap((id) => {
    const group = groups.find((g) => g.id !== "season" && g.options.some((o) => o.id === id));
    const option = group?.options.find((o) => o.id === id);
    return group && option
      ? [
          <RemovableChip
            key={id}
            label={`${group.label}: ${option.label}`}
            removeLabel={`Remove ${group.label}: ${option.label}`}
            onRemove={() => toggleFilterId(id)}
          />,
        ]
      : [];
  });
}

/** The stats, pinned players and teams that are part of the query, each removable. */
function ChosenChips() {
  const { state, toggleStatId, unpinPlayer, toggleTeamId } = useQueryState();
  const leagueName = useLeagueName();
  const pinned = usePinnedPlayers(state.players);
  return (
    <>
      {state.subject === "teams"
        ? state.teams.map((id) => {
            const name = TEAMS.find((t) => t.id === id)?.name ?? id;
            return <RemovableChip key={id} label={name} removeLabel={`Remove ${name}`} onRemove={() => toggleTeamId(id)} />;
          })
        : pinned.map((p) => {
            const name = p.full_name ?? p.gsis_id;
            return <RemovableChip key={p.gsis_id} label={name} removeLabel={`Unpin ${name}`} onRemove={() => unpinPlayer(p.gsis_id)} />;
          })}
      {state.stats.map((id) => {
        const stat = getStatById(id);
        const name = stat ? statLabel(stat, leagueName) : id;
        return <RemovableChip key={id} label={name} removeLabel={`Remove ${name}`} onRemove={() => toggleStatId(id)} />;
      })}
    </>
  );
}

/** The whole query as a row of chips: who, which stats, how, when, for whom, ranked how, and which situations. */
export function QueryBar({ playerSearch }: { playerSearch: PlayerSearchProps }) {
  return (
    <div role="group" aria-label="Query" className="flex flex-wrap items-center gap-2">
      <SubjectChip playerSearch={playerSearch} />
      <ChosenChips />
      <AddChipTrigger label="+ stat" ariaLabel="Add a stat">
        <StatPicker />
      </AddChipTrigger>
      <span aria-hidden className="mx-1 hidden h-6 w-px bg-line md:block" />
      <GranularityChip />
      <SeasonChip />
      <PositionChip />
      <LeagueChip />
      <RankingChip />
      <ActiveFilterChips />
      <AddChipTrigger label="+ filter" ariaLabel="Add a situation filter">
        <FilterPopover />
      </AddChipTrigger>
    </div>
  );
}
