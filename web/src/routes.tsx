import type { ReactNode } from "react";
import { createBrowserRouter, type RouteObject } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAdmin } from "@/components/layout/RequireAdmin";
import { RequireSession } from "@/components/layout/RequireSession";
import { redirectRoutes } from "@/lib/redirects";
import { NAV_ITEMS, type NavPath } from "@/nav";
import Admin from "@/pages/Admin";
import Ask from "@/pages/Ask";
import DevViz from "@/pages/DevViz";
import Explore from "@/pages/Explore";
import Lineup from "@/pages/Lineup";
import Login from "@/pages/Login";
import Moves from "@/pages/Moves";
import MyLeagues from "@/pages/MyLeagues";
import NotFound from "@/pages/NotFound";
import Player from "@/pages/Player";
import Players from "@/pages/Players";
import PlayersCompare from "@/pages/PlayersCompare";
import RedeemInvite from "@/pages/RedeemInvite";
import Scorecard from "@/pages/Scorecard";
import Season from "@/pages/Season";
import ThisWeek from "@/pages/ThisWeek";

/** The five tabs. Add a page here and in nav.ts. */
const TABS: Record<NavPath, ReactNode> = {
  "/": <ThisWeek />,
  "/lineup": <Lineup />,
  "/moves": <Moves />,
  "/season": <Season />,
  "/players": <Players />,
};

export const routes: RouteObject[] = [
  // the two pages a signed-out visitor can reach: sign in, and the page an invite link opens
  { path: "/login", element: <Login /> },
  { path: "/invite/:token", element: <RedeemInvite /> },
  {
    element: <RequireSession />,
    children: [
      {
        element: <AppShell />,
        children: [
          ...NAV_ITEMS.map(({ path }) => ({ path, element: TABS[path] })),
          { path: "/players/find", element: <Explore /> },
          { path: "/players/compare", element: <PlayersCompare /> },
          { path: "/players/:gsisId", element: <Player /> },
          { path: "/ask", element: <Ask /> },
          { path: "/model", element: <Scorecard /> },
          { path: "/my-leagues", element: <MyLeagues /> },
          { element: <RequireAdmin />, children: [{ path: "/admin", element: <Admin /> }] },
          ...redirectRoutes,
          ...(import.meta.env.DEV ? [{ path: "/dev/viz", element: <DevViz /> }] : []),
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
