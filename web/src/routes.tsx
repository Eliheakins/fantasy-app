import { lazy, type ReactNode, Suspense } from "react";
import { createBrowserRouter, type RouteObject } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAdmin } from "@/components/layout/RequireAdmin";
import { RequireSession } from "@/components/layout/RequireSession";
import { RouteError } from "@/components/layout/RouteError";
import { redirectRoutes } from "@/lib/redirects";
import { NAV_ITEMS, type NavPath } from "@/nav";
import DevViz from "@/pages/DevViz";
import Login from "@/pages/Login";
import MyLeagues from "@/pages/MyLeagues";
import NotFound from "@/pages/NotFound";
import RedeemInvite from "@/pages/RedeemInvite";

// Pages load on demand so the first paint ships only the shell. Navigation suspends inside a router transition,
// so the old page stays up (and focus lands on the new h1) once the chunk arrives; the AppShell Suspense covers first load.
const Admin = lazy(() => import("@/pages/Admin"));
const Ask = lazy(() => import("@/pages/Ask"));
const Explore = lazy(() => import("@/pages/Explore"));
const Lineup = lazy(() => import("@/pages/Lineup"));
const Moves = lazy(() => import("@/pages/Moves"));
const Player = lazy(() => import("@/pages/Player"));
const Players = lazy(() => import("@/pages/Players"));
const PlayersCompare = lazy(() => import("@/pages/PlayersCompare"));
const Scorecard = lazy(() => import("@/pages/Scorecard"));
const Season = lazy(() => import("@/pages/Season"));
const ThisWeek = lazy(() => import("@/pages/ThisWeek"));
const WelcomeDialog = lazy(() => import("@/features/leagues/WelcomeDialog").then((m) => ({ default: m.WelcomeDialog })));

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
        element: (
          <>
            <AppShell />
            <Suspense fallback={null}>
              <WelcomeDialog />
            </Suspense>
          </>
        ),
        // a page chunk that 404s after a redeploy lands here instead of React Router's default screen
        errorElement: <RouteError />,
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
