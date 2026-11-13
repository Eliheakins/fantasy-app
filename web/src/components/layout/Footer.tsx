import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "react-router";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { LOCAL_EMAIL, signOut, useSession } from "@/lib/session";
import { navSearch } from "./navLinks";
import { linkButtonClass } from "@/components/ui/styles";
import { cn } from "@/lib/utils";

/** Model scorecard link, data freshness per source, who is signed in, and the attribution Sleeper asks for. */
export function Footer() {
  const state = useEnvelopeQuery("/api/status");
  const { search, pathname } = useLocation();
  const session = useSession();
  const queryClient = useQueryClient();
  const history = new URLSearchParams(navSearch("/ask", search, pathname));
  history.set("tab", "history");
  const historySearch = history.toString();
  const rows = state.kind === "ready" ? state.data.freshness : [];
  // a laptop run with no accounts answers as "local": there is nobody to sign out
  const account = session.kind === "signedIn" && session.me.email !== LOCAL_EMAIL ? session.me : null;
  return (
    <footer className="mx-auto w-full max-w-page border-t border-line px-4 py-3 text-caption text-muted">
      <Link to={{ pathname: "/model", search: navSearch("/model", search, pathname) }} className={cn("mr-4", linkButtonClass)}>
        Model scorecard
      </Link>
      <Link to={{ pathname: "/ask", search: navSearch("/ask", search, pathname) }} className={cn("mr-4", linkButtonClass)}>
        Ask
      </Link>
      <Link to={{ pathname: "/ask", search: historySearch }} className={cn("mr-4", linkButtonClass)}>
        Ask history
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
          <Link to="/my-leagues" className={linkButtonClass}>
            My leagues
          </Link>
          {account.is_admin && (
            <Link to="/admin" className={linkButtonClass}>
              Admin
            </Link>
          )}
          <button type="button" className={linkButtonClass} onClick={() => void signOut(queryClient)}>
            Sign out
          </button>
          <button type="button" className={linkButtonClass} onClick={() => void signOut(queryClient, true)}>
            Sign out everywhere
          </button>
        </span>
      )}
    </footer>
  );
}
