import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import type { Status } from "@/api/types";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { LOCAL_EMAIL, signOut, useSession } from "@/lib/session";
import { navSearch } from "./navLinks";

/** Model scorecard link, data freshness per source, who is signed in, and the attribution Sleeper asks for. */
export function Footer() {
  const state = useEnvelopeQuery<Status>("/api/status");
  const { search, pathname } = useLocation();
  const session = useSession();
  const queryClient = useQueryClient();
  const rows = state.kind === "ready" ? state.data.freshness : [];
  // a laptop run with no accounts answers as "local": there is nobody to sign out
  const account = session.kind === "signedIn" && session.me.email !== LOCAL_EMAIL ? session.me : null;
  return (
    <footer className="mx-auto w-full max-w-[1200px] border-t border-line px-4 py-3 text-caption text-muted">
      <Link
        to={{ pathname: "/model", search: navSearch("/model", search, pathname) }}
        className="mr-4 inline-flex min-h-[44px] items-center underline"
      >
        Model scorecard
      </Link>
      {rows.map((r) => (
        <span key={r.source} className="mr-4 inline-block">
          {r.source}: {r.age_hours.toFixed(1)} hours ago
        </span>
      ))}
      <span className="mr-4">Data from Sleeper and nflverse.</span>
      {account && (
        <span className="inline-flex items-center gap-3">
          <span>{account.email}</span>
          <Link to="/my-leagues" className="inline-flex min-h-[44px] items-center underline">
            My leagues
          </Link>
          {account.is_admin && (
            <Link to="/admin" className="inline-flex min-h-[44px] items-center underline">
              Admin
            </Link>
          )}
          <button type="button" className="inline-flex min-h-[44px] items-center underline" onClick={() => void signOut(queryClient)}>
            Sign out
          </button>
          <button type="button" className="inline-flex min-h-[44px] items-center underline" onClick={() => void signOut(queryClient, true)}>
            Sign out everywhere
          </button>
        </span>
      )}
    </footer>
  );
}
