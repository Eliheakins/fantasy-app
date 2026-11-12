import { isPending } from "@/api/envelope";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import type { components } from "@/api/schema";
import type { ActionRow } from "@/features/thisweek/leagues/logic";
import type { DigestData } from "@/lib/digestTypes";
import { useAllLeagues, useEachLeague } from "@/lib/league";
import { phaseOf } from "@/features/effects/phase";
import { deadlineWeekState } from "@/lib/deadline";
import { useNow } from "./useNow";
import { type Todo, holeTodos, leagueTodos, orderByDeadline, tradeDeadlineTodos } from "./todos";
import { type WeekCalendar, leagueName, lineupDeadlineDay, waiverDeadlineDay } from "./weekLogic";

type HoleRow = components["schemas"]["HoleRow"];

export type TodosState = {
  /** Still waiting for any league's lists. */
  pending: boolean;
  /** Every to-do of both leagues, expiring first and then biggest effect first. */
  todos: Todo[];
  /** Names of leagues whose actions, digest or holes did not load. */
  failed: string[];
  calendar: WeekCalendar | null;
  calendarFailed: boolean;
  /** Message when the league list itself did not load: then there are no to-dos to show. */
  leaguesError: string | null;
  now: Date;
};

/** Both leagues' to-dos in one ordered list, plus the week calendar their deadlines come from. */
export function useTodos(): TodosState {
  const leagues = useAllLeagues();
  const calendarState = useEnvelopeQuery<WeekCalendar>("/api/week-calendar");
  const list = leagues.kind === "ready" ? leagues.data : [];
  const keys = list.map((l) => l.league_key);
  const actions = useEachLeague<ActionRow[]>(keys, "actions?stored_adds=true");
  const digests = useEachLeague<DigestData>(keys, "digest");
  const holes = useEachLeague<HoleRow[]>(keys, "holes");
  const calendar = calendarState.kind === "ready" ? calendarState.data : null;
  const now = useNow();
  const failed: string[] = [];
  const all = list.flatMap((l, i) => {
    const a = actions[i];
    const d = digests[i];
    const h = holes[i];
    if (a?.kind === "error" || d?.kind === "error" || h?.kind === "error") failed.push(leagueName(l));
    const waiverDay = calendar?.waivers.find((w) => w.league_key === l.league_key)?.day_of_week ?? null; // null for daily waivers
    const deadlines = {
      lineup: calendar ? lineupDeadlineDay(calendar.kickoffs, now) : null,
      waiver: waiverDeadlineDay(waiverDay, now),
    };
    const phase = phaseOf(l, d?.kind === "ready" ? d.data.odds_change : []);
    const digest = d?.kind === "ready" ? d.data : null;
    const state = deadlineWeekState(l.current_week, l.trade_deadline, l.playoff_week_start == null ? null : l.playoff_week_start - 1);
    return [
      ...holeTodos(l, h?.kind === "ready" ? h.data : [], deadlines.lineup),
      ...leagueTodos(l, a?.kind === "ready" ? a.data : [], digest?.waivers ?? [], deadlines, phase),
      ...tradeDeadlineTodos(l, digest?.trades ?? [], state, l.trade_deadline ?? null, deadlines.waiver, phase),
    ];
  });
  const pending = isPending(leagues) || actions.some(isPending) || digests.some(isPending) || holes.some(isPending);
  const leaguesError = leagues.kind === "error" ? leagues.error.message : leagues.kind === "no_data" ? leagues.message : null;
  return { pending, todos: orderByDeadline(all), failed, calendar, calendarFailed: calendarState.kind === "error", leaguesError, now };
}
