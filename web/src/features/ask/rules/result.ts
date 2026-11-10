import { getStatById } from "@/stat/config/statDictionary";
import type { QueryIntent } from "@/stat/lib/schemas/nlqIntent";
import type { GranularityMode, Side } from "@/stat/types/queryBuilder";

import { leaderboardFor } from "../ranking";
import type { Entities } from "./entities";
import type { FilterReads } from "./filters";
import { splitsByLocation } from "./settings";
import type { SplitRead } from "./split";
import { ambiguous, type RuleResult } from "./types";
import { unique } from "./vocab";

/** The filter chips in reading order: phrases, season years, then the time and opponent chips. */
function filterIds(e: Entities, filters: FilterReads, split: SplitRead): string[] {
  const { found, years, time } = filters;
  const byLocation = splitsByLocation(split);
  const filterAt: { at: number; id: string }[] = [
    ...found.flatMap((f) =>
      f.piece.kind === "chips"
        ? f.piece.ids.filter((id) => !(byLocation && id.startsWith("loc-"))).map((id) => ({ at: f.at, id }))
        : [],
    ),
    ...years.map((y) => ({ at: y.at, id: `season-${y.year}` })),
    ...time.filters.map((id) => ({ at: time.used[0] ?? 0, id })),
    ...e.opponents.filters.map((id) => ({ at: e.opponents.used[0] ?? 0, id })),
  ];
  return unique(filterAt.sort((a, b) => a.at - b.at).map((f) => f.id));
}

/** Puts the stats, filters, granularity and any team or ranking reading together as the final answer. */
export function buildResult(
  e: Entities,
  filters: FilterReads,
  split: SplitRead,
  side: Side,
  statIds: readonly string[],
  granularity: GranularityMode,
): RuleResult {
  const intent: QueryIntent = {
    stat_ids: [...statIds],
    filter_ids: filterIds(e, filters, split),
    granularity,
  };
  if (e.asksTeams && statIds.some((id) => getStatById(id)?.category.startsWith("ngs_"))) {
    return {
      status: "unsupported",
      reason: "Next Gen Stats are per-player weekly values, so a team has no total for them.",
    };
  }
  const team = e.asksTeams ? { team: { ids: unique(e.teams.map((t) => t.id)), side } } : {};
  if (!e.isLeaderboard) {
    return { status: "resolved", intent, ...team };
  }
  const leaderboard = leaderboardFor(e.tokens, statIds[0]!, granularity, {
    teams: e.asksTeams,
    defense: side === "defense",
    weekly: split.split === "week",
  });
  if ("reason" in leaderboard) {
    return ambiguous(leaderboard.reason);
  }
  // "rushers by EPA" ranks the rushers' own EPA: the ranked stat takes the first stat's place.
  const ranked = { ...intent, stat_ids: unique([leaderboard.order.metric, ...statIds.slice(1)]) };
  return { status: "resolved", intent: ranked, leaderboard, ...team };
}
