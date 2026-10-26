import type { RosterRow } from "./logic";
import { splitRoster } from "./logic";

const ROW = "grid min-h-[44px] grid-cols-[minmax(0,1fr)_5.5rem_6rem] items-center gap-x-3 py-1";

function Group({ title, rows }: { title: string; rows: readonly RosterRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="mt-2 first:mt-0">
      <h4 className="text-caption font-semibold text-muted">{title}</h4>
      <ul aria-label={title} className="divide-y divide-border border-y border-border">
        {rows.map((r) => (
          <li key={r.sleeper_id} className={ROW}>
            <span className="break-words">{r.full_name ?? "Unknown"}</span>
            <span className="whitespace-nowrap text-caption text-muted">
              {r.position ?? "–"} · {r.team ?? "FA"}
            </span>
            <span className="text-caption">
              {r.injury_status && <span className="rounded border border-border px-1">{r.injury_status}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Starters then bench; each row has fixed columns so positions and injury tags line up. */
export function RosterList({ rows }: { rows: readonly RosterRow[] }) {
  const { starters, bench } = splitRoster(rows);
  return (
    <>
      <Group title="Starters" rows={starters} />
      <Group title="Bench" rows={bench} />
    </>
  );
}
