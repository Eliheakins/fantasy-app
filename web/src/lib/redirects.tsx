import { Navigate, type RouteObject, useLocation } from "react-router";

/** Sends an old path to its new home, keeping every query param (league, team, week, Explore's own) and adding `set`. */
function KeepQuery({ to, set = {} }: { to: string; set?: Record<string, string> }) {
  const { search: current, hash } = useLocation();
  const params = new URLSearchParams(current);
  Object.entries(set).forEach(([key, value]) => params.set(key, value));
  const search = params.toString();
  return <Navigate to={{ pathname: to, search: search ? `?${search}` : "", hash }} replace />;
}

const to = (path: string, set?: Record<string, string>) => <KeepQuery to={path} set={set} />;

/** Routes for the paths of the earlier layout, so bookmarks and shared links keep working. */
export const redirectRoutes: RouteObject[] = [
  { path: "/waivers", element: to("/moves", { view: "fa" }) },
  { path: "/trades", element: to("/moves", { view: "trades" }) },
  { path: "/outlook", element: to("/season") },
  { path: "/scoreboard", element: to("/season") },
  { path: "/league", element: to("/season") },
  { path: "/digest", element: to("/") },
  { path: "/scorecard", element: to("/model") },
  { path: "/explore", element: to("/players/find") },
];
