import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { formatNumber } from "@/viz";
import type { WatchRow } from "./types";

const COLUMNS: Column<WatchRow>[] = [
  { label: "Player", role: "primary", render: (r) => `${r.full_name} (${r.position})` },
  { label: "Rest of season", numeric: true, render: (r) => formatNumber(r.ros_points) },
  { label: "Why", render: (r) => r.reasons.join("; ") },
];

/** My players with a falling snap share or market value, or an injury flag. */
export function Watch({ rows }: { rows: readonly WatchRow[] }) {
  if (rows.length === 0) return <p className="text-body text-muted">No one on your roster is flagged.</p>;
  return <ResponsiveTable caption="Players to watch" columns={COLUMNS} rows={rows} rowKey={(r) => r.gsis_id} />;
}
