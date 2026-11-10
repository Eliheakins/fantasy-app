import { Suspense, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Loading } from "@/components/ApiBoundary";
import { Footer } from "./Footer";
import { navSearch } from "./navLinks";
import { NoLeaguesNotice } from "./NoLeaguesNotice";
import { StatusBanner } from "./StatusBanner";
import { TeamBanner } from "./TeamBanner";
import { TopBar } from "./TopBar";
import { useRouteAnnounce } from "@/hooks/useRouteAnnounce";
import { TeamProvider } from "@/lib/TeamProvider";
import { useTeam } from "@/lib/teamContext";
import { NAV_ITEMS } from "@/nav";
import { cn } from "@/lib/utils";

/** True once the page has scrolled, so the sticky header's shadow deepens over the content. */
function useScrolled(): boolean {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 0);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return scrolled;
}

function Frame() {
  const { search, pathname } = useLocation(); // nav links keep only ?league=, ?team= and ?week=
  const { viewed } = useTeam();
  useRouteAnnounce(viewed ? (viewed.team_name ?? `Team ${viewed.roster_id}`) : null);
  const scrolled = useScrolled();
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-focus focus:px-4 focus:py-3 focus:text-white"
      >
        Skip to content
      </a>
      <div
        data-scrolled={scrolled || undefined}
        className="on-chrome bg-forest text-white shadow-[0_2px_6px_rgba(19,32,26,0.18)] transition-shadow md:sticky md:top-0 md:z-30 data-[scrolled]:md:shadow-[0_4px_16px_rgba(19,32,26,0.28)]"
      >
        <TopBar />
        <nav aria-label="Main" className="hidden bg-chrome-tabs md:block">
          <ul className="mx-auto flex w-full max-w-[1200px] gap-8 px-[var(--page-pad)]">
            {NAV_ITEMS.map(({ path, label }) => (
              <li key={path}>
                <NavLink
                  to={{ pathname: path, search: navSearch(path, search, pathname) }}
                  end={path === "/"}
                  className={({ isActive }) =>
                    cn(
                      "flex min-h-[48px] items-center border-b-[3px] pt-[3px] text-[15px] leading-6",
                      isActive ? "border-chrome-accent font-semibold text-white" : "border-transparent text-chrome-text hover:text-white",
                    )
                  }
                >
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <div className="tab-bar-offset flex min-w-0 flex-1 flex-col md:pb-0">
        <StatusBanner />
        <NoLeaguesNotice />
        <TeamBanner />
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1200px] flex-1 outline-none">
          <Suspense fallback={<Loading />}>
            <Outlet />
          </Suspense>
        </main>
        <Footer />
      </div>
      <nav
        aria-label="Main tabs"
        className="tab-bar on-chrome fixed inset-x-0 bottom-0 z-10 flex bg-forest shadow-[0_-2px_6px_rgba(19,32,26,0.18)] md:hidden"
      >
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={{ pathname: path, search: navSearch(path, search, pathname) }}
            end={path === "/"}
            className={({ isActive }) =>
              cn(
                "tab-link flex min-h-[56px] min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-body",
                isActive ? "font-semibold text-white" : "text-chrome-text",
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

/** Forest header band with the tab row as its second row, sticky from 768 px up; below that the tabs move to a Forest bottom bar. */
export function AppShell() {
  return (
    <TeamProvider>
      <Frame />
    </TeamProvider>
  );
}
