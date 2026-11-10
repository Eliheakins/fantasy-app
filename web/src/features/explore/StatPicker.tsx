import { useState } from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { STAT_CATEGORY_LABELS, STAT_CATEGORY_ORDER, getStatsByCategory } from "@/stat/config/statDictionary";
import { MAX_SELECTED_STATS } from "@/stat/lib/queryUrl";
import { useQueryState } from "@/stat/react/useQueryState";

/** Search every stat by name or description, grouped by category; a click adds or removes it. */
export function StatPicker() {
  const { state, toggleStatId } = useQueryState();
  const [search, setSearch] = useState("");
  const needle = search.trim().toLowerCase();
  const atCap = state.stats.length >= MAX_SELECTED_STATS;

  const groups = STAT_CATEGORY_ORDER.map((cat) => ({
    cat,
    stats: getStatsByCategory(cat).filter(
      (s) => needle === "" || `${s.label} ${s.description ?? ""} ${s.help ?? ""}`.toLowerCase().includes(needle),
    ),
  })).filter((g) => g.stats.length > 0);

  return (
    <div className="space-y-2">
      <Input
        type="search"
        aria-label="Search stats"
        placeholder="Search stats, e.g. targets"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {groups.length === 0 && <p className="py-3 text-muted">No stat matches “{search}”.</p>}
      {groups.map(({ cat, stats }) => (
        <section key={cat} aria-label={STAT_CATEGORY_LABELS[cat]}>
          <h3 className="px-1 pt-2 text-caption font-semibold uppercase tracking-wide text-muted">{STAT_CATEGORY_LABELS[cat]}</h3>
          <ul className="flex flex-col gap-0.5">
            {stats.map((s) => {
              const chosen = state.stats.includes(s.id);
              const blocked = !chosen && atCap;
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    aria-pressed={chosen}
                    disabled={blocked}
                    onClick={() => toggleStatId(s.id)}
                    className={cn(
                      "flex min-h-11 w-full items-center gap-3 rounded-lg px-2.5 py-1.5 text-left hover:bg-panel disabled:cursor-not-allowed disabled:opacity-50",
                      chosen && "bg-panel",
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold text-ink">{s.label}</span>
                      {(s.help ?? s.description) && <span className="block text-caption text-muted">{s.help ?? s.description}</span>}
                    </span>
                    <span className={cn("shrink-0 text-caption font-semibold", chosen ? "text-forest" : "text-focus")}>
                      {chosen ? "Added" : "Add"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      <p className="border-t border-line pt-2 text-caption text-muted">
        {state.stats.length} of {MAX_SELECTED_STATS} stats chosen
        {atCap ? ". Remove one to add another." : ""}
      </p>
    </div>
  );
}
