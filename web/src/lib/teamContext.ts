import { createContext, useContext } from "react";
import type { components } from "@/api/schema";

export type TeamRow = components["schemas"]["TeamRow"];

export type TeamContextValue = {
  /** Roster id being viewed, or null for my team (the default; nothing is sent). */
  team: number | null;
  /** The league the team belongs to (the selected league). */
  league: string | null;
  teams: TeamRow[];
  /** The viewed team's row, only when it is not mine. */
  viewed: TeamRow | null;
  setTeam: (rosterId: number | null) => void;
  /** One-line notice when the link named a team that is not in this league; cleared by dismissNotice. */
  notice: string | null;
  dismissNotice: () => void;
};

export const NO_TEAM: TeamContextValue = { team: null, league: null, teams: [], viewed: null, setTeam: () => {}, notice: null, dismissNotice: () => {} };
export const TeamContext = createContext<TeamContextValue>(NO_TEAM);

/** Defaults to my team when there is no provider (tests, pages rendered alone). */
export function useTeam(): TeamContextValue {
  return useContext(TeamContext);
}
