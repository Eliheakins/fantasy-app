import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Footer } from "./Footer";
import { navSearch } from "./navLinks";
import { StatusBanner } from "./StatusBanner";
import { TeamBanner } from "./TeamBanner";
import { TopBar } from "./TopBar";
import { useRouteAnnounce } from "@/hooks/useRouteAnnounce";
import { TeamProvider } from "@/lib/TeamProvider";
import { useTeam } from "@/lib/teamContext";
import { NAV_ITEMS } from "@/nav";
import { cn } from "@/lib/utils";

function Frame() {
  const { search, pathname } = useLocation(); // nav links keep only ?league=, ?team= and ?week=
  const { viewed } = useTeam();
  useRouteAnnounce(viewed ? (viewed.team_name ?? `Team ${viewed.roster_id}`) : null);
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-focus focus:px-4 focus:py-3 focus:text-white"
      >
        Skip to content
      </a>
      <TopBar />
      <nav aria-label="Main" className="hidden border-b border-line md:block">
        <ul className="mx-auto flex w-full max-w-[1200px] gap-6 px-4">
          {NAV_ITEMS.map(({ path, label }) => (
            <li key={path}>
              <NavLink
                to={{ pathname: path, search: navSearch(path, search, pathname) }}
                end={path === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex min-h-[44px] items-center border-b-2 text-body",
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
      <div className="tab-bar-offset flex min-w-0 flex-1 flex-col md:pb-0">
        <StatusBanner />
        <TeamBanner />
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1200px] flex-1 outline-none">
          <Outlet />
        </main>
        <Footer />
      </div>
      <nav aria-label="Main tabs" className="tab-bar fixed inset-x-0 bottom-0 z-10 flex border-t border-line bg-page md:hidden">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={{ pathname: path, search: navSearch(path, search, pathname) }}
            end={path === "/"}
            className={({ isActive }) =>
              cn(
                "tab-link flex min-h-[56px] min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-body",
                isActive ? "font-semibold text-ink" : "text-muted",
              )
            }
          >
            <Icon size={20} aria-hidden />
            <span className="tab-label">{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

/** Forest band and tab row from 768 px up; the band collapses and the tabs move to a bottom bar below. */
export function AppShell() {
  return (
    <TeamProvider>
      <Frame />
    </TeamProvider>
  );
}
