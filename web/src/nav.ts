import { ClipboardList, House, ListOrdered, Repeat, TrendingUp, Trophy, UserPlus, Users } from "lucide-react";

/** Nav entries for the rail and tab bar. Add a page here and in routes.tsx. */
export const NAV_ITEMS = [
  { path: "/", label: "Home", icon: House },
  { path: "/lineup", label: "Lineup", icon: ClipboardList },
  { path: "/waivers", label: "Waivers", icon: UserPlus },
  { path: "/trades", label: "Trades", icon: Repeat },
  { path: "/outlook", label: "Outlook", icon: TrendingUp },
  { path: "/scoreboard", label: "Scores", icon: ListOrdered },
  { path: "/league", label: "League", icon: Trophy },
  { path: "/players", label: "Players", icon: Users },
] as const;
