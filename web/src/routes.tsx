import type { ReactNode } from "react";
import { createBrowserRouter, type RouteObject } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { redirectRoutes } from "@/lib/redirects";
import { NAV_ITEMS, type NavPath } from "@/nav";
import Ask from "@/pages/Ask";
import DevViz from "@/pages/DevViz";
import Explore from "@/pages/Explore";
import Lineup from "@/pages/Lineup";
import Moves from "@/pages/Moves";
import NotFound from "@/pages/NotFound";
import Player from "@/pages/Player";
import Players from "@/pages/Players";
import PlayersCompare from "@/pages/PlayersCompare";
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
  {
    element: <AppShell />,
    children: [
      ...NAV_ITEMS.map(({ path }) => ({ path, element: TABS[path] })),
      { path: "/players/find", element: <Explore /> },
      { path: "/players/compare", element: <PlayersCompare /> },
      { path: "/players/:gsisId", element: <Player /> },
      { path: "/ask", element: <Ask /> },
      { path: "/model", element: <Scorecard /> },
      ...redirectRoutes,
      ...(import.meta.env.DEV ? [{ path: "/dev/viz", element: <DevViz /> }] : []),
      { path: "*", element: <NotFound /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
