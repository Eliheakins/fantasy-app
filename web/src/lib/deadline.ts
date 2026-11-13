import { LAST_WEEK } from "@/lib/week";

export type DeadlineWeekState = "open" | "closing" | "passed" | "none";

/**
 * Where the trade deadline stands. `tradeDeadline` is the last week trades are allowed; a null deadline, or one
 * past the last regular-season week (Sleeper uses 99 for "no deadline"), is "none". "passed" is the API's rule
 * (`week > deadline`, api_routes/season.py); "closing" is the deadline week itself.
 */
export function deadlineWeekState(
  currentWeek: number | null | undefined,
  tradeDeadline: number | null | undefined,
  lastRegularWeek: number | null | undefined,
): DeadlineWeekState {
  if (tradeDeadline == null || tradeDeadline > (lastRegularWeek ?? LAST_WEEK) || currentWeek == null) return "none";
  if (currentWeek > tradeDeadline) return "passed";
  return currentWeek === tradeDeadline ? "closing" : "open";
}
