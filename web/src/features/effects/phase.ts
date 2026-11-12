import type { components } from "@/api/schema";

type OddsRow = components["schemas"]["OddsChangeRow"];

/** season: seeds still move (playoff odds). playoffs: seeds are fixed (title odds). out: my team cannot win the title. */
export type Phase = "season" | "playoffs" | "out";

export const OUT_MESSAGE = "You are out of the playoffs";

/**
 * From `playoff_week_start` Sleeper's bracket fixes the seeds, so playoff odds are 0 or 1 for everyone and only
 * the title odds still say anything. A title chance of exactly 0 in a refresh from that week means eliminated.
 */
export function phaseOf(
  league: { current_week?: number | null; playoff_week_start?: number | null } | undefined,
  odds: readonly Pick<OddsRow, "is_me" | "as_of_week" | "p_title">[],
): Phase {
  const start = league?.playoff_week_start;
  if (start == null || league?.current_week == null || league.current_week < start) return "season";
  const me = odds.find((o) => o.is_me);
  return me !== undefined && me.as_of_week >= start && me.p_title === 0 ? "out" : "playoffs";
}
