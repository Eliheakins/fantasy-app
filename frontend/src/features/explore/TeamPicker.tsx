import { ToggleGroup, ToggleGroupItem } from "@/shared/components/ui/toggle-group";
import { TEAMS } from "@/shared/config/teams";
import { MAX_PINNED_TEAMS } from "@/shared/lib/queryUrl";
import { useQueryState } from "@/shared/lib/useQueryState";

/**
 * Picks up to MAX_PINNED_TEAMS teams and whether to count their offense or their defense (what
 * opponents gained against them). With none picked, a ranking covers every team.
 */
export function TeamPicker() {
  const { state, toggleTeamId, setSide } = useQueryState();
  const full = state.teams.length >= MAX_PINNED_TEAMS;

  return (
    <div className="space-y-3">
      <ToggleGroup
        type="single"
        value={state.side}
        onValueChange={(side) => {
          if (side === "offense" || side === "defense") {
            setSide(side);
          }
        }}
        className="flex gap-2"
        aria-label="Offense or defense"
      >
        <ToggleGroupItem value="offense" className="rounded-md">
          Offense
        </ToggleGroupItem>
        <ToggleGroupItem value="defense" className="rounded-md">
          Defense (allowed)
        </ToggleGroupItem>
      </ToggleGroup>
      <ToggleGroup
        type="multiple"
        value={state.teams}
        onValueChange={(next) => {
          // One click changes one team; find it and toggle it through the URL.
          const changed = [...next.filter((id) => !state.teams.includes(id)), ...state.teams.filter((id) => !next.includes(id))];
          changed.forEach((id) => toggleTeamId(id));
        }}
        className="grid grid-cols-4 gap-1.5"
        aria-label="Teams"
      >
        {TEAMS.map((team) => (
          <ToggleGroupItem
            key={team.id}
            value={team.id}
            disabled={full && !state.teams.includes(team.id)}
            aria-label={team.name}
            title={team.name}
            className="rounded-md px-1 text-xs data-[disabled]:cursor-not-allowed data-[disabled]:opacity-40"
          >
            {team.id}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <p className="text-[10px] text-ink-muted">
        Pick up to {MAX_PINNED_TEAMS} teams to compare, or none and set a ranking to rank all 32.
      </p>
    </div>
  );
}
