import { useId, useState } from "react";
import { MAX_TRADE_IDS, toggleId } from "./logic";

export type Option = { id: string; label: string };

type MultiSelectProps = {
  legend: string;
  options: readonly Option[];
  selected: readonly string[];
  onChange: (next: readonly string[]) => void;
  max?: number;
};

/** A filterable checkbox list: native keyboard and screen-reader behaviour, 44 px rows. */
export function MultiSelect({ legend, options, selected, onChange, max = MAX_TRADE_IDS }: MultiSelectProps) {
  const [filter, setFilter] = useState("");
  const filterId = useId();
  const shown = options.filter((o) => o.label.toLowerCase().includes(filter.trim().toLowerCase()));
  const full = selected.length >= max;
  return (
    <fieldset className="min-w-0 rounded border border-border p-2">
      <legend className="px-1 text-body font-semibold">{legend}</legend>
      <label htmlFor={filterId} className="sr-only">
        Filter {legend}
      </label>
      <input
        id={filterId}
        type="search"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter players"
        className="mb-1 h-[44px] w-full rounded border border-border bg-page px-2"
      />
      <p className="py-1 text-caption text-muted" aria-live="polite">
        {selected.length} selected (up to {max}){full ? ", the limit is reached" : ""}
      </p>
      <ul className="max-h-64 overflow-y-auto">
        {shown.map((o) => {
          const checked = selected.includes(o.id);
          return (
            <li key={o.id}>
              <label className="flex min-h-[44px] cursor-pointer items-center gap-3 px-1">
                <input
                  type="checkbox"
                  className="size-[22px] shrink-0"
                  checked={checked}
                  disabled={full && !checked}
                  onChange={() => onChange(toggleId(selected, o.id, max))}
                />
                <span>{o.label}</span>
              </label>
            </li>
          );
        })}
        {shown.length === 0 && <li className="py-2 text-muted">No players match.</li>}
      </ul>
    </fieldset>
  );
}
