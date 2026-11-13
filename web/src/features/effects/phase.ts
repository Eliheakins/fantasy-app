import type { components } from "@/api/schema";

type TeamPhase = components["schemas"]["LeagueRow"]["team_phase"];

/**
 * season: seeds still move (playoff odds). playoffs: my team still plays for something (title odds; a bye or a
 * consolation game counts). out: eliminated from the title. over: the playoffs are finished for everyone.
 */
export type Phase = "season" | "playoffs" | "out" | "over";

export const OUT_MESSAGE = "You are out of the playoffs";
export const SEASON_OVER = "Your season is over";

const FROM_TEAM_PHASE: Record<NonNullable<TeamPhase>, Phase> = {
  regular: "season",
  playing: "playoffs",
  bye: "playoffs",
  consolation: "playoffs",
  eliminated: "out",
  champion: "over",
  over: "over",
};

/** No add, trade or lineup hole matters any more: the team is out or the season is over. */
export const isDone = (phase: Phase): boolean => phase === "out" || phase === "over";

/**
 * From the server's `team_phase` (bracket evidence). When it is unknown the week decides, and an unknown phase
 * is never "out": a missing to-do in a game week costs more than an extra one.
 */
export function phaseOf(
  league: { current_week?: number | null; playoff_week_start?: number | null; team_phase?: TeamPhase } | undefined,
): Phase {
  const known = league?.team_phase;
  if (known != null) return FROM_TEAM_PHASE[known];
  const start = league?.playoff_week_start;
  return start == null || league?.current_week == null || league.current_week < start ? "season" : "playoffs";
}
