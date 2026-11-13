import { createContext, useContext, useEffect, useRef, useState } from "react";
import { matchRoutes, useLocation } from "react-router-dom";
import { PAGE_HEADING_ID } from "@/components/PageHeader";
import { EXTRA_TITLES, NAV_ITEMS, PUBLIC_TITLES } from "@/nav";

const SITE = "Fantasy";
const NOT_FOUND_TITLE = "Page not found";

const TITLES: Readonly<Record<string, string>> = {
  ...Object.fromEntries(NAV_ITEMS.map((n) => [n.path, n.title])),
  ...EXTRA_TITLES,
  ...PUBLIC_TITLES,
};
// matchRoutes ranks the patterns, so "/players/find" wins over "/players/:gsisId"
const TITLED_ROUTES = Object.keys(TITLES).map((path) => ({ path }));

/** The page name for a path: its nav.ts title, else "Page not found". */
export function pageTitle(pathname: string): string {
  const path = matchRoutes(TITLED_ROUTES, pathname)?.[0]?.route.path;
  return (path && TITLES[path]) ?? NOT_FOUND_TITLE;
}

/** "Lineup · Fantasy", with the viewed team inserted when it is not mine. */
export function documentTitle(pageName: string, viewedTeam: string | null): string {
  return [pageName, viewedTeam, SITE].filter(Boolean).join(" · ");
}

type PageName = { pathname: string; name: string };

/** Provided by the shell around its pages: how a page hands `useRouteAnnounce` the name it learns once loaded. */
export const PageNameContext = createContext<(name: PageName | null) => void>(() => {});

/** Names the current page in the document title (the player page: the player's name); its nav.ts title stands while null. */
export function usePageName(name: string | null): void {
  const setName = useContext(PageNameContext);
  const { pathname } = useLocation();
  useEffect(() => {
    if (name === null) return;
    setName({ pathname, name });
    return () => setName(null);
  }, [setName, pathname, name]);
}

/** The one owner of document.title: the route's nav.ts title, or the name its page gave (`usePageName`). Also moves
 * focus to the page heading when the path changes (not on first load, not when only the query string changes), so
 * keyboard and screen-reader users land on new content. Returns the setter to provide as `PageNameContext`. */
export function useRouteAnnounce(viewedTeam: string | null): (name: PageName | null) => void {
  const { pathname } = useLocation();
  const [named, setNamed] = useState<PageName | null>(null);
  // a name is kept for the path it was given on, so the next page never shows the last one's name
  const name = named?.pathname === pathname ? named.name : pageTitle(pathname);
  const first = useRef(true);
  useEffect(() => {
    document.title = documentTitle(name, viewedTeam);
  }, [name, viewedTeam]);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    (document.getElementById(PAGE_HEADING_ID) ?? document.getElementById("main"))?.focus();
  }, [pathname]);
  return setNamed;
}
