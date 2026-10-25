import type { RosterRow } from "./logic";

/** Stacked rows work as the table on desktop and the card list on a phone. */
export function RosterList({ rows }: { rows: readonly RosterRow[] }) {
  return (
    <ul aria-label="Roster" className="divide-y divide-border border-y border-border">
      {rows.map((r) => (
        <li key={r.sleeper_id} className="flex min-h-[44px] flex-wrap items-center gap-x-3 gap-y-0 py-1">
          <span className="min-w-[10rem] flex-1 break-words">{r.full_name ?? "Unknown"}</span>
          <span className="whitespace-nowrap text-caption text-muted">
            {r.position ?? "–"} · {r.team ?? "FA"}
          </span>
          <span className="text-caption">
            {r.injury_status && (
              <span className="rounded border border-border px-1">{r.injury_status}</span>
            )}
          </span>
          <span className="text-caption text-muted">{r.is_starter ? "Starting" : ""}</span>
        </li>
      ))}
    </ul>
  );
}
