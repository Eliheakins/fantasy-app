import { FILTER_CHIP_GROUPS } from "@/config/queryBuilderOptions";
import { useQueryBuilderStore } from "@/store/useQueryBuilderStore";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

/**
 * The Context — grouped multi-select chips (Radix ToggleGroup type="multiple") for WHERE predicates.
 */
export function FilterChipsBar() {
  const filterState = useQueryBuilderStore((s) => s.filterChipState);
  const applyFilterGroup = useQueryBuilderStore((s) => s.applyFilterGroup);

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">The Context</h2>
      <p className="mt-0.5 text-xs text-zinc-600">
        Toggle filters for the WHERE clause. Within each row, multiple selections join with{" "}
        <span className="text-zinc-400">OR</span> (or <span className="text-zinc-400">AND</span> where
        noted). Rows combine with <span className="text-zinc-400">AND</span>.
      </p>
      <p className="mt-2 text-[11px] leading-snug text-amber-600/90">
        Some columns (e.g. <code className="text-amber-500/90">posteam_type</code>,{" "}
        <code className="text-amber-500/90">season_type</code>,{" "}
        <code className="text-amber-500/90">xyac_mean_yardage</code>) may need to be added to your PBP
        Parquet pipeline before queries succeed.
      </p>

      <div className="mt-5 flex flex-col gap-5">
        {FILTER_CHIP_GROUPS.map((group) => {
          const optionIds = group.options.map((o) => o.id);
          const value = optionIds.filter((id) => Boolean(filterState[id]));

          return (
            <div key={group.id}>
              <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  {group.label}
                </h3>
                {group.description ? (
                  <span className="text-[10px] text-zinc-600">({group.description})</span>
                ) : null}
                <span className="text-[10px] text-zinc-600">
                  join: <span className="text-zinc-400">{group.combine.toUpperCase()}</span>
                </span>
              </div>
              <ToggleGroup
                type="multiple"
                value={value}
                onValueChange={(next) => applyFilterGroup(group, next)}
                className="flex flex-wrap justify-start gap-2"
                size="sm"
                aria-label={group.label}
              >
                {group.options.map((chip) => (
                  <ToggleGroupItem
                    key={chip.id}
                    value={chip.id}
                    aria-label={chip.label}
                    className="rounded-full border-zinc-700 data-[state=on]:border-emerald-600/50"
                  >
                    {chip.label}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </div>
          );
        })}
      </div>
    </section>
  );
}
