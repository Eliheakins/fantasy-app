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

/** Routes in the shell that are not tabs: reached from the top bar Ask box, the footer, and Players. routes.tsx mounts
 * a page at each key. The player page's title stands until it names the player (`usePageName`). */
export const EXTRA_TITLES = {
  "/admin": "Admin",
  "/ask": "Ask",
  "/my-leagues": "My leagues",
  "/model": "Model scorecard",
  "/players/find": "Find players",
  "/players/compare": "Compare players",
  "/players/:gsisId": "Player",
} as const satisfies Readonly<Record<string, string>>;

export type ExtraPath = keyof typeof EXTRA_TITLES;

/** The pages a signed-out visitor can reach, outside the shell: sign in, and the page an invite link opens. */
export const PUBLIC_TITLES = {
  "/login": "Sign in",
  "/invite/:token": "Choose a password",
} as const satisfies Readonly<Record<string, string>>;

export type PublicPath = keyof typeof PUBLIC_TITLES;

/** The routes whose data follows the global ?week=; the week select is disabled elsewhere. */
export const WEEK_PATHS: readonly string[] = ["/lineup", "/season"];
