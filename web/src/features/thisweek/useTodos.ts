import type { ApiState } from "@/api/envelope";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import type { ActionRow } from "@/features/thisweek/leagues/logic";
import type { DigestData } from "@/lib/digestTypes";
import { useAllLeagues, useEachLeague } from "@/lib/league";
import { useNow } from "./useNow";
import { type Todo, leagueTodos, orderByDeadline } from "./todos";
import { type WeekCalendar, lineupDeadlineDay, waiverDeadlineDay } from "./weekLogic";

const isOpen = (s: ApiState<unknown>) => s.kind === "loading" || s.kind === "running";

export type TodosState = {
  /** Still waiting for any league's lists. */
  pending: boolean;
  /** Every to-do of both leagues, expiring first and then biggest effect first. */
  todos: Todo[];
  /** Names of leagues whose actions or digest did not load. */
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
  const calendar = calendarState.kind === "ready" ? calendarState.data : null;
  const now = useNow();
  const failed: string[] = [];
  const all = list.flatMap((l, i) => {
    const a = actions[i];
    const d = digests[i];
    if (a?.kind === "error" || d?.kind === "error") failed.push(l.name?.trim() || l.league_key);
    const waiverDay = calendar?.waivers.find((w) => w.league_key === l.league_key)?.day_of_week ?? null; // null for daily waivers
    const deadlines = {
      lineup: calendar ? lineupDeadlineDay(calendar.kickoffs, now) : null,
      waiver: waiverDeadlineDay(waiverDay, now),
    };
    return leagueTodos(l, a?.kind === "ready" ? a.data : [], d?.kind === "ready" ? d.data.waivers : [], deadlines);
  });
  const pending = isOpen(leagues) || actions.some(isOpen) || digests.some(isOpen);
  const leaguesError = leagues.kind === "error" ? leagues.error.message : leagues.kind === "no_data" ? leagues.message : null;
  return { pending, todos: orderByDeadline(all), failed, calendar, calendarFailed: calendarState.kind === "error", leaguesError, now };
}
