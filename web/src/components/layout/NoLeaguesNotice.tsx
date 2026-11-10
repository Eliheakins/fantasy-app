import { Link } from "react-router-dom";
import { useLeague } from "@/lib/league";

/** For an account that can see no league yet (a new friend): say so, and where to add one, instead
 * of leaving every page to report that it has no data. */
export function NoLeaguesNotice() {
  const { leagues } = useLeague();
  if (leagues.kind !== "ready" || leagues.data.length > 0) return null;
  return (
    <p
      role="status"
      className="flex min-h-[44px] flex-wrap items-center gap-x-3 border-b border-l-4 border-line border-l-focus bg-panel px-4 text-body"
    >
      <span>You have no leagues yet.</span>
      <Link to="/my-leagues" className="inline-flex min-h-[44px] items-center underline">
        Add your Sleeper league
      </Link>
    </p>
  );
}
