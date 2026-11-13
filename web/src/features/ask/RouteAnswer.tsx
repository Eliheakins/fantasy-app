import { Link } from "react-router-dom";

import { navSearch, type PageUrl } from "@/components/layout/navLinks";

import type { FantasyRoute } from "./fantasyRoute";

type Props = { route: FantasyRoute; here: PageUrl };

/** A fantasy question answered by the page that has it; the link keeps the league and team. */
export function RouteAnswer({ route, here: { pathname, search } }: Props) {
  const [path, query = ""] = (route.to ?? "").split("?");
  const params = new URLSearchParams(navSearch(path ?? "", search, pathname));
  new URLSearchParams(query).forEach((value, key) => params.set(key, value));
  const to = `${path ?? ""}${params.toString() ? `?${params.toString()}` : ""}`;
  return (
    <section aria-label="Answer" className="space-y-1 border-t border-line pt-3">
      <p className="text-body text-ink">
        {route.text}{" "}
        {route.to && route.label ? (
          <Link to={to} className="font-medium text-ink underline underline-offset-2">
            Open {route.label}
          </Link>
        ) : null}
      </p>
      <p className="text-caption text-muted">Read by the built-in rules; the model is not asked about your league.</p>
    </section>
  );
}
