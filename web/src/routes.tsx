import type { ReactNode } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { NAV_ITEMS } from "@/nav";
import DevViz from "@/pages/DevViz";
import Home from "@/pages/Home";
import Lineup from "@/pages/Lineup";
import Outlook from "@/pages/Outlook";
import Players from "@/pages/Players";
import Trades from "@/pages/Trades";
import Waivers from "@/pages/Waivers";

/** Page agents register their page component here and touch no other shared file. */
const PAGES: Record<(typeof NAV_ITEMS)[number]["path"], ReactNode> = {
  "/": <Home />,
  "/lineup": <Lineup />,
  "/waivers": <Waivers />,
  "/trades": <Trades />,
  "/outlook": <Outlook />,
  "/players": <Players />,
};

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      ...NAV_ITEMS.map(({ path }) => ({ path, element: PAGES[path] })),
      { path: "/dev/viz", element: <DevViz /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
