import type { ReactNode } from "react";
import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { NAV_ITEMS, type NavPath } from "@/nav";
import Ask from "@/pages/Ask";
import Explore from "@/pages/Explore";
import DevViz from "@/pages/DevViz";
import Digest from "@/pages/Digest";
import Home from "@/pages/Home";
import NotFound from "@/pages/NotFound";
import League from "@/pages/League";
import Lineup from "@/pages/Lineup";
import Outlook from "@/pages/Outlook";
import Players from "@/pages/Players";
import Scorecard from "@/pages/Scorecard";
import Scoreboard from "@/pages/Scoreboard";
import Trades from "@/pages/Trades";
import Waivers from "@/pages/Waivers";

/** Page agents register their page component here and touch no other shared file. */
const PAGES: Record<NavPath, ReactNode> = {
  "/": <Home />,
  "/lineup": <Lineup />,
  "/waivers": <Waivers />,
  "/trades": <Trades />,
  "/outlook": <Outlook />,
  "/scoreboard": <Scoreboard />,
  "/league": <League />,
  "/digest": <Digest />,
  "/players": <Players />,
  "/explore": <Explore />,
  "/ask": <Ask />,
  "/scorecard": <Scorecard />,
};

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      ...NAV_ITEMS.map(({ path }) => ({ path, element: PAGES[path] })),
      ...(import.meta.env.DEV ? [{ path: "/dev/viz", element: <DevViz /> }] : []),
      { path: "*", element: <NotFound /> },
    ],
  },
]);
