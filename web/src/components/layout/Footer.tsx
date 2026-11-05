import { Link, useLocation } from "react-router-dom";
import type { Status } from "@/api/types";
import { useApi } from "@/hooks/useApi";
import { navSearch } from "./navLinks";

/** Model scorecard link, data freshness per source and the attribution Sleeper asks for. */
export function Footer() {
  const state = useApi<Status>("/api/status");
  const { search, pathname } = useLocation();
  const rows = state.kind === "ready" ? state.data.freshness : [];
  return (
    <footer className="mx-auto w-full max-w-[1200px] border-t border-line px-4 py-3 text-caption text-muted">
      <Link to={{ pathname: "/model", search: navSearch("/model", search, pathname) }} className="mr-4 inline-flex min-h-[44px] items-center underline">
        Model scorecard
      </Link>
      {rows.map((r) => (
        <span key={r.source} className="mr-4 inline-block">
          {r.source}: {r.age_hours.toFixed(1)} hours ago
        </span>
      ))}
      <span>Data from Sleeper and nflverse.</span>
    </footer>
  );
}
