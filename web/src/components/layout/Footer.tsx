import type { Status } from "@/api/types";
import { useApi } from "@/hooks/useApi";

/** Data freshness per source plus the attribution Sleeper asks for. */
export function Footer() {
  const state = useApi<Status>("/api/status");
  const rows = state.kind === "ready" ? state.data.freshness : [];
  return (
    <footer className="border-t border-border px-4 py-2 text-caption text-muted">
      {rows.map((r) => (
        <span key={r.source} className="mr-4 inline-block">
          {r.source}: {r.age_hours.toFixed(1)} hours ago
        </span>
      ))}
      <span>Data from Sleeper and nflverse.</span>
    </footer>
  );
}
