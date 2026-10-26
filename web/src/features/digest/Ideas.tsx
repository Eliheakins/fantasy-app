import { useState } from "react";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { classifyChange } from "@/features/waivers/logic";
import { Delta, formatNumber } from "@/viz";
import { formatAge, ideasNotice } from "./logic";
import type { IdeasInfo, MoveIdeaRow } from "./types";

function Change({ change, error }: { change: number | null; error?: number | null }) {
  const c = classifyChange(change, error);
  if (c.kind === "missing") return <span>–</span>;
  if (c.kind === "noise") return <span className="text-mark-muted tabular-nums">{c.noiseText}</span>;
  return <Delta points={c.points} />;
}

const WAIVER_COLUMNS: Column<MoveIdeaRow>[] = [
  { label: "Add", role: "primary", render: (r) => r.get },
  { label: "Drop", render: (r) => r.give },
  { label: "Extra points", numeric: true, render: (r) => (r.delta_points === null ? "–" : <Delta points={r.delta_points} />) },
  { label: "Playoff odds change (% pts)", numeric: true, render: (r) => <Change change={r.playoff_delta} /> },
  { label: "Title odds change (% pts)", numeric: true, render: (r) => <Change change={r.title_delta} error={r.se_title} /> },
  {
    label: "Title error (± % pts)",
    numeric: true,
    role: "detail",
    render: (r) => (r.se_title === null ? "–" : `±${formatNumber(r.se_title * 100)}`),
  },
];

const TRADE_COLUMNS: Column<MoveIdeaRow>[] = [
  { label: "Trade partner", role: "primary", render: (r) => r.partner ?? "–" },
  { label: "You give", render: (r) => r.give },
  { label: "You get", render: (r) => r.get },
  { label: "Playoff odds change (% pts)", numeric: true, render: (r) => <Change change={r.playoff_delta} /> },
  { label: "Title odds change (% pts)", numeric: true, render: (r) => <Change change={r.title_delta} error={r.se_title} /> },
];

const asOf = (iso: string) =>
  new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** When the ideas were made: date, age and the week of the refresh. Nothing without a stored time. */
export function AsOf({ info }: { info: IdeasInfo }) {
  const [now] = useState(() => Date.now());
  if (info.created_at === null || !info.is_mine) return null;
  return (
    <p className="mb-2 text-caption text-muted">
      As of {asOf(info.created_at)} ({formatAge(info.created_at, now)}), week {info.as_of_week} refresh.
    </p>
  );
}

type Props = { kind: "waiver" | "trade"; rows: readonly MoveIdeaRow[]; info: IdeasInfo };

/** One list of stored ideas, or the reason there is none. A stale list is still shown, under its notice. */
export function Ideas({ kind, rows, info }: Props) {
  const notice = ideasNotice(info, kind);
  const blocked = !info.is_mine || info.created_at === null || (kind === "trade" && info.deadline_passed);
  const noun = kind === "waiver" ? "waiver adds" : "trade ideas";
  return (
    <>
      {notice && <p role="status" className="measure mb-2 border-l-4 border-warning bg-surface px-3 py-2 text-body">{notice}</p>}
      {!blocked && rows.length === 0 && <p className="text-body text-muted">No {noun} cleared the bar at the last refresh.</p>}
      {!blocked && rows.length > 0 && (
        <ResponsiveTable
          caption={kind === "waiver" ? "Top waiver adds" : "Top trade ideas"}
          columns={kind === "waiver" ? WAIVER_COLUMNS : TRADE_COLUMNS}
          rows={rows}
          rowKey={(r) => `${r.kind}-${r.rank}`}
        />
      )}
    </>
  );
}
