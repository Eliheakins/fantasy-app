import { Delta, formatNumber } from "@/viz";
import { classifyChange, type WaiverRow } from "./logic";

function Change({ change, error }: { change: number | null; error?: number | null }) {
  const c = classifyChange(change, error);
  if (c.kind === "missing") return <span>–</span>;
  if (c.kind === "noise") return <span className="text-mark-muted tabular-nums">{c.noiseText}</span>;
  return <Delta points={c.points} />;
}

type Props = {
  rows: readonly WaiverRow[];
  selected: string | null;
  onSelect: (gsisId: string) => void;
};

const BTN =
  "min-h-[44px] text-left font-medium underline-offset-2 hover:underline focus-visible:outline-2";

export function AddsTable({ rows, selected, onSelect }: Props) {
  const pick = (r: WaiverRow) => (
    <button type="button" className={BTN} aria-pressed={selected === r.gsis_id} onClick={() => onSelect(r.gsis_id)}>
      {r.full_name}
    </button>
  );
  return (
    <>
      <table className="hidden w-full text-body md:table">
        <thead>
          <tr className="text-left text-caption text-muted">
            <th scope="col">Add</th>
            <th scope="col">Pos</th>
            <th scope="col">Drop</th>
            <th scope="col">Extra points</th>
            <th scope="col">Playoffs</th>
            <th scope="col">Title</th>
            <th scope="col">Title error</th>
            <th scope="col">Sleeper adds</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.gsis_id} className={selected === r.gsis_id ? "bg-surface" : undefined}>
              <td>{pick(r)}</td>
              <td>{r.position}</td>
              <td>{r.drop_name}</td>
              <td><Delta points={r.delta_points} /></td>
              <td><Change change={r.playoff_delta} /></td>
              <td><Change change={r.title_delta} error={r.se_title} /></td>
              <td className="tabular-nums">{r.se_title == null ? "–" : `±${formatNumber(r.se_title * 100)}`}</td>
              <td className="tabular-nums">{r.trending_adds ?? "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="space-y-2 md:hidden">
        {rows.map((r) => (
          <li key={r.gsis_id} className="rounded border border-border p-3">
            <div>{pick(r)} <span className="text-muted">{r.position}</span></div>
            <div className="text-caption text-muted">Drop {r.drop_name}</div>
            <dl className="mt-1 grid grid-cols-2 gap-x-3 text-body">
              <dt className="text-muted">Extra points</dt><dd><Delta points={r.delta_points} /></dd>
              <dt className="text-muted">Playoffs</dt><dd><Change change={r.playoff_delta} /></dd>
              <dt className="text-muted">Title</dt><dd><Change change={r.title_delta} error={r.se_title} /></dd>
              <dt className="text-muted">Title error</dt>
              <dd className="tabular-nums">{r.se_title == null ? "–" : `±${formatNumber(r.se_title * 100)}`}</dd>
              <dt className="text-muted">Sleeper adds</dt><dd className="tabular-nums">{r.trending_adds ?? "–"}</dd>
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}

