import { useFilterChipGroups } from "@/stat/react/filterChipGroups";
import { useQueryState } from "@/stat/react/useQueryState";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";

/** Filters people reach for most; the rest sit under "More situations". Season has its own chip. */
const COMMON_GROUP_IDS = ["season_type", "week_number", "opponent", "location", "field"];

function GroupChoices({ group }: { group: FilterChipGroup }) {
  const { filterChipState, applyFilterGroup } = useQueryState();
  const optionIds = group.options.map((o) => o.id);
  const value = optionIds.filter((id) => Boolean(filterChipState[id]));
  return (
    <fieldset className="space-y-1.5 border-0 p-0">
      <legend className="text-caption font-semibold text-ink">{group.label}</legend>
      <ToggleGroup
        type="multiple"
        value={value}
        onValueChange={(next) => applyFilterGroup(optionIds, next)}
        className="flex flex-wrap justify-start gap-1.5"
        size="sm"
        aria-label={group.label}
      >
        {group.options.map((chip) => (
          <ToggleGroupItem key={chip.id} value={chip.id} aria-label={chip.label} className="rounded-full data-[state=on]:border-focus/50">
            {chip.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </fieldset>
  );
}

/** Situation filters: the common ones first, the rest folded away. */
export function FilterPopover() {
  const groups = useFilterChipGroups().filter((g) => g.id !== "season");
  const common = COMMON_GROUP_IDS.flatMap((id) => groups.filter((g) => g.id === id));
  const more = groups.filter((g) => !COMMON_GROUP_IDS.includes(g.id));
  return (
    <div className="space-y-4">
      {common.map((g) => (
        <GroupChoices key={g.id} group={g} />
      ))}
      <details className="border-t border-line pt-2">
        <summary className="flex min-h-11 cursor-pointer items-center font-semibold text-focus">More situations</summary>
        <div className="space-y-4 pt-2">
          {more.map((g) => (
            <GroupChoices key={g.id} group={g} />
          ))}
        </div>
      </details>
    </div>
  );
}
