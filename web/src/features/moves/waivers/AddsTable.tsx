import { PlayerLink } from "@/components/PlayerLink";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { Delta, formatNumber } from "@/viz";
import { classifyChange } from "@/features/effects/change";
import type { WaiverRow } from "./logic";

function Change({ change, error }: { change: number | null; error?: number | null }) {
  const c = classifyChange(change, error);
  if (c.kind === "missing") return <span>–</span>;
  if (c.kind === "noise") return <span className="text-muted tabular-nums">{c.noiseText}</span>;
  return <Delta points={c.points} />;
}

type Props = {
  rows: readonly WaiverRow[];
  selected: string | null;
  onSelect: (gsisId: string) => void;
};

const BTN = "min-h-[44px] text-left font-medium underline decoration-line underline-offset-4 hover:decoration-ink lg:min-h-0";

function columns(selected: string | null, onSelect: (id: string) => void): Column<WaiverRow>[] {
  return [
    {
      label: "Add",
      role: "primary",
      render: (r) => (
        <>
          <PlayerLink gsisId={r.gsis_id} name={r.full_name} position={r.position} />{" "}
          <span className="text-caption font-normal text-muted">{r.position}</span>{" "}
          <button
            type="button"
            className={BTN}
            aria-label={`Details for ${r.full_name}`}
            aria-pressed={selected === r.gsis_id}
            onClick={() => onSelect(r.gsis_id)}
          >
            Details
          </button>
        </>
      ),
    },
    { label: "Drop", render: (r) => r.drop_name },
    { label: "Extra points", numeric: true, render: (r) => <Delta points={r.delta_points} /> },
    { label: "Playoff odds change (% pts)", numeric: true, render: (r) => <Change change={r.playoff_delta} /> },
    { label: "Title odds change (% pts)", numeric: true, render: (r) => <Change change={r.title_delta} error={r.se_title} /> },
    {
      label: "Title error (± % pts)",
      numeric: true,
      role: "detail",
      render: (r) => (r.se_title == null ? "–" : `±${formatNumber(r.se_title * 100)}`),
    },
    {
      label: "Sleeper adds",
      numeric: true,
      role: "detail",
      render: (r) => (r.trending_adds == null ? "–" : r.trending_adds.toLocaleString("en-US")),
    },
  ];
}

/** The selected row gets the strong left bar and weight. */
export function AddsTable({ rows, selected, onSelect }: Props) {
  return (
    <ResponsiveTable
      caption="Free agent adds"
      columns={columns(selected, onSelect)}
      rows={rows}
      rowKey={(r) => r.gsis_id}
      isStrong={(r) => r.gsis_id === selected}
    />
  );
}
