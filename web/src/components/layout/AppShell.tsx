import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Footer } from "./Footer";
import { StatusBanner } from "./StatusBanner";
import { TeamBanner } from "./TeamBanner";
import { TopBar } from "./TopBar";
import { useRouteAnnounce } from "@/hooks/useRouteAnnounce";
import { TeamProvider } from "@/lib/TeamProvider";
import { useTeam } from "@/lib/teamContext";
import { NAV_ITEMS } from "@/nav";
import { cn } from "@/lib/utils";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-2 text-body",
    isActive ? "font-semibold text-accent" : "text-muted hover:text-text",
  );

function Frame() {
  const { search } = useLocation(); // nav links keep ?team= and ?league=
  const { viewed } = useTeam();
  useRouteAnnounce(viewed ? (viewed.team_name ?? `Team ${viewed.roster_id}`) : null);
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-accent focus:px-4 focus:py-3 focus:text-accent-fg"
      >
        Skip to content
      </a>
      <nav aria-label="Main" className="hidden w-48 shrink-0 border-r border-border p-4 md:block">
        <ul className="flex flex-col gap-1">
          {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
            <li key={path}>
              <NavLink to={{ pathname: path, search }} end={path === "/"} className={(s) => cn(linkClass(s), "min-h-[44px] px-2")}>
                <Icon size={16} aria-hidden /> {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="tab-bar-offset flex min-w-0 flex-1 flex-col md:pb-0">
        <TopBar />
        <StatusBanner />
        <TeamBanner />
        <main id="main" tabIndex={-1} className="flex-1 outline-none">
          <Outlet />
        </main>
        <Footer />
      </div>
      <nav aria-label="Main tabs" className="tab-bar fixed inset-x-0 bottom-0 z-10 flex border-t border-border bg-page md:hidden">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={{ pathname: path, search }}
            end={path === "/"}
            className={(s) => cn(linkClass(s), "tab-link min-h-[56px] min-w-0 flex-1 flex-col justify-center gap-0.5")}
          >
            <Icon size={20} aria-hidden />
            <span className="tab-label">{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

/** Left rail from 768 px up, bottom tab bar below. */
export function AppShell() {
  return (
    <TeamProvider>
      <Frame />
    </TeamProvider>
  );
}
