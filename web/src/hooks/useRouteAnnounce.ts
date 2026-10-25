import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { PAGE_HEADING_ID } from "@/components/PageHeader";
import { NAV_ITEMS } from "@/nav";

const SITE = "Fantasy";
export const NOT_FOUND_TITLE = "Page not found";

/** The page name for a path: the nav entry's title, else "Page not found". */
export function pageTitle(pathname: string): string {
  const item = NAV_ITEMS.find((n) => n.path === pathname);
  if (!item) return NOT_FOUND_TITLE;
  return item.title;
}

/** "Lineup · Fantasy", with the viewed team inserted when it is not mine. */
export function documentTitle(pathname: string, viewedTeam: string | null): string {
  return [pageTitle(pathname), viewedTeam, SITE].filter(Boolean).join(" · ");
}

/** Sets document.title per route, and moves focus to the page heading when the path changes
 * (not on first load, not when only the query string changes), so keyboard and screen-reader users land on new content. */
export function useRouteAnnounce(viewedTeam: string | null): void {
  const { pathname } = useLocation();
  const first = useRef(true);
  useEffect(() => {
    document.title = documentTitle(pathname, viewedTeam);
  }, [pathname, viewedTeam]);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    (document.getElementById(PAGE_HEADING_ID) ?? document.getElementById("main"))?.focus();
  }, [pathname]);
}
