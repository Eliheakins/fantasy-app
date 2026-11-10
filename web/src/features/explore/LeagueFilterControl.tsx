import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useLeagueOwners } from "@/features/explore/useLeagueOwners";
import { useQueryState } from "@/stat/react/useQueryState";
import { useTeam } from "@/lib/teamContext";
import type { RosterFilter } from "@/stat/lib/queryUrl";

const ALL = "all";
const FILTERS: readonly RosterFilter[] = ["mine", "rostered", "fa"];

/** Restricts player rows to today's league rosters. Rosters are as of now, so the wording says so. */
export function LeagueFilterControl() {
  const { state, setRoster } = useQueryState();
  const { league, unmatched } = useLeagueOwners();
  const { viewed } = useTeam();
  if (league === null || state.subject === "teams") {
    return null;
  }
  const labels: Record<RosterFilter, string> = {
    mine: viewed?.team_name ? `${viewed.team_name} now` : "My roster now",
    rostered: "Rostered now",
    fa: "Free agents now",
  };

  return (
    <div className="space-y-1">
      <h3 className="text-caption font-semibold uppercase tracking-wide text-focus">League</h3>
      <p className="text-caption text-muted">
        Today&apos;s rosters, whatever season you are looking at. It narrows pinned players and rankings.
      </p>
      <ToggleGroup
        type="single"
        value={state.roster ?? ALL}
        onValueChange={(value) => {
          if (value === ALL) {
            setRoster(null);
          } else if (FILTERS.some((f) => f === value)) {
            setRoster(value as RosterFilter);
          }
        }}
        className="flex flex-wrap gap-2"
        aria-label="League"
      >
        <ToggleGroupItem value={ALL} className="rounded-md">
          All players
        </ToggleGroupItem>
        {FILTERS.map((f) => (
          <ToggleGroupItem key={f} value={f} className="rounded-md">
            {labels[f]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {unmatched > 0 && (
        <p className="text-caption text-muted">
          {unmatched} rostered {unmatched === 1 ? "player" : "players"} could not be matched and may appear as free agents.
        </p>
      )}
    </div>
  );
}
