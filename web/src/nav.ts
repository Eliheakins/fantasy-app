import { ClipboardList, Compass, Gauge, House, ListOrdered, Newspaper, Repeat, TrendingUp, Trophy, UserPlus, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/** Rail groups in display order. */
export const NAV_GROUPS = ["Decide", "Season", "Research"] as const;
export type NavGroup = (typeof NAV_GROUPS)[number];

type NavItem = {
  path: string;
  label: string;
  icon: LucideIcon;
  /** The h1 and document title. */
  title: string;
  group: NavGroup;
  /** Gets its own tab on phones; the rest sit behind "More". */
  tab?: true;
};

/** Nav entries for the rail, tab bar and More sheet. Add a page here and in routes.tsx. (Ask joins Research in the Ask slice.) */
export const NAV_ITEMS = [
  { path: "/", label: "Home", icon: House, title: "Home", group: "Decide", tab: true },
  { path: "/lineup", label: "Lineup", icon: ClipboardList, title: "Lineup", group: "Decide", tab: true },
  { path: "/waivers", label: "Waivers", icon: UserPlus, title: "Waivers", group: "Decide", tab: true },
  { path: "/trades", label: "Trades", icon: Repeat, title: "Trades", group: "Decide", tab: true },
  { path: "/outlook", label: "Outlook", icon: TrendingUp, title: "Outlook", group: "Season" },
  { path: "/scoreboard", label: "Scores", icon: ListOrdered, title: "Scoreboard", group: "Season" },
  { path: "/league", label: "League", icon: Trophy, title: "League", group: "Season" },
  { path: "/digest", label: "Digest", icon: Newspaper, title: "Weekly digest", group: "Season" },
  { path: "/players", label: "Players", icon: Users, title: "Player outlook", group: "Research" },
  { path: "/explore", label: "Explore", icon: Compass, title: "Explore", group: "Research" },
  { path: "/scorecard", label: "Model", icon: Gauge, title: "Model scorecard", group: "Research" },
] as const satisfies readonly NavItem[];

export type NavPath = (typeof NAV_ITEMS)[number]["path"];

const ITEMS: readonly NavItem[] = NAV_ITEMS;
export const TAB_ITEMS = ITEMS.filter((i) => i.tab);
export const MORE_ITEMS = ITEMS.filter((i) => !i.tab);
