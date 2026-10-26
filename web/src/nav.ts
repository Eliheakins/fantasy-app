import { ClipboardList, House, ListOrdered, Newspaper, Repeat, TrendingUp, Trophy, UserPlus, Users } from "lucide-react";

/** Nav entries for the rail and tab bar. `title` is the h1 and document title. Add a page here and in routes.tsx. */
export const NAV_ITEMS = [
  { path: "/", label: "Home", icon: House, title: "Home" },
  { path: "/lineup", label: "Lineup", icon: ClipboardList, title: "Lineup" },
  { path: "/waivers", label: "Waivers", icon: UserPlus, title: "Waivers" },
  { path: "/trades", label: "Trades", icon: Repeat, title: "Trades" },
  { path: "/outlook", label: "Outlook", icon: TrendingUp, title: "Outlook" },
  { path: "/scoreboard", label: "Scores", icon: ListOrdered, title: "Scoreboard" },
  { path: "/league", label: "League", icon: Trophy, title: "League" },
  { path: "/digest", label: "Digest", icon: Newspaper, title: "Weekly digest" },
  { path: "/players", label: "Players", icon: Users, title: "Player outlook" },
] as const;
