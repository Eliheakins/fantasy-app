import { ArrowRight, Search } from "lucide-react";
import { Link, NavLink } from "react-router-dom";
import { navSearch, type PageUrl } from "@/components/layout/navLinks";
import { cn } from "@/lib/utils";

const ITEMS = [
  { path: "/players", label: "Your players" },
  { path: "/players/find", label: "Find players" },
] as const;

/** The Players tab's two modes as a second row of tabs, styled like the main tabs. */
export function PlayersNav({ here: { search, pathname } }: { here: PageUrl }) {
  return (
    <nav aria-label="Players" className="mb-6">
      <ul className="flex gap-8 border-b border-line">
        {ITEMS.map(({ path, label }) => (
          <li key={path}>
            <NavLink
              to={{ pathname: path, search: navSearch(path, search, pathname) }}
              end
              className={({ isActive }) =>
                cn(
                  "-mb-px flex min-h-[48px] items-center border-b-[3px] pt-[3px] text-[15px] leading-6",
                  isActive ? "border-forest font-semibold text-ink" : "border-transparent text-muted hover:text-ink",
                )
              }
            >
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** A row on Your players pointing at the stat finder, which a text link in the header made easy to miss. */
export function FindPlayersCta({ here: { search, pathname } }: { here: PageUrl }) {
  return (
    <Link
      to={{ pathname: "/players/find", search: navSearch("/players/find", search, pathname) }}
      className="group mb-8 flex min-h-[56px] max-w-2xl items-center gap-3 rounded-full border border-panel-line bg-surface px-5 py-2 text-body hover:border-forest hover:bg-panel"
    >
      <Search aria-hidden size={18} className="shrink-0 text-forest" />
      <span className="min-w-0 flex-1">
        <span className="font-semibold text-ink">Find players by any stat</span>
        <span className="hidden text-muted sm:inline"> · EPA, YAC, separation, league points, any season</span>
      </span>
      <ArrowRight aria-hidden size={18} className="shrink-0 text-forest transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}
