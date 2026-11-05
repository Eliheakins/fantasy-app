import { ClipboardList, House, Repeat, TrendingUp, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

type NavItem = {
  path: string;
  label: string;
  icon: LucideIcon;
  /** The document title. */
  title: string;
};

/** The five tabs, in display order: the top row from md up, the bottom bar on phones. Add a page here and in routes.tsx. */
export const NAV_ITEMS = [
  { path: "/", label: "This week", icon: House, title: "This week" },
  { path: "/lineup", label: "Lineup", icon: ClipboardList, title: "Lineup" },
  { path: "/moves", label: "Moves", icon: Repeat, title: "Moves" },
  { path: "/season", label: "Season", icon: TrendingUp, title: "Season" },
  { path: "/players", label: "Players", icon: Users, title: "Players" },
] as const satisfies readonly NavItem[];

export type NavPath = (typeof NAV_ITEMS)[number]["path"];

/** Routes that are not tabs: reached from the top bar Ask box, the footer, and Players. */
export const EXTRA_TITLES: Readonly<Record<string, string>> = {
  "/ask": "Ask",
  "/model": "Model scorecard",
  "/players/find": "Find players",
};

/** The routes whose data follows the global ?week=; the week select is disabled elsewhere. */
export const WEEK_PATHS: readonly string[] = ["/lineup", "/season"];
