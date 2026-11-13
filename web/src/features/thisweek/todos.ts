import type { components } from "@/api/schema";
import { actionGain, actionSentence, worthActing } from "@/features/thisweek/leagues/logic";
import type { ActionRow } from "@/features/thisweek/leagues/logic";
import { compareEffect, type Effect, effectOf, MIN_PLAYOFF_GAIN } from "@/features/effects/effect";
import { type EffectWhy, lineupWhy, tradeWhy, waiverWhy } from "@/features/effects/explain";
import { type Phase, isDone } from "@/features/effects/phase";
import type { DeadlineWeekState } from "@/lib/deadline";
import { sleeperLeagueUrl } from "@/lib/sleeper";
import { leagueName } from "./weekLogic";

type MoveIdea = components["schemas"]["MoveIdeaRow"];

type TodoKind = "waiver" | "lineup" | "injury" | "trade" | "cover" | "ir";
type HoleRow = components["schemas"]["HoleRow"];
export type Todo = {
  id: string;
  leagueKey: string;
  leagueName: string;
  kind: TodoKind;
  title: string;
  detail: string;
  href: string;
  effect: Effect;
  why?: EffectWhy;
  /** New York calendar day the to-do stops being possible; null when not known. */
  deadlineDay: string | null;
  /** The league page in Sleeper; null when the league id is not known. */
  sleeperUrl: string | null;
  /** Free agents to add for a lineup hole, one line each; an empty list means none can start. */
  fillIns?: string[];
};

export const FILL_IN_LABEL = "Add in Sleeper before kickoff; it may need a waiver claim";
export const NO_FILL_IN = "No free agent left to start this week";

const HOLE_REASON = { bye: "is on bye", out: "is out", empty: "", ir_move: "" } as const;
const PTS = (n: number) => n.toFixed(1);

/** The odds an idea is judged on: title in the playoffs (playoff odds are fixed then), playoff odds before. */
const ideaOdds = (idea: MoveIdea, phase: Phase) => (phase !== "season" ? idea.title_delta : idea.playoff_delta);

/** The idea with the biggest odds change; none for an eliminated team or after the season. */
const bestIdea = (ideas: readonly MoveIdea[], phase: Phase): MoveIdea | undefined =>
  isDone(phase)
    ? undefined
    : ideas.reduce<MoveIdea | undefined>(
        (best, w) => ((ideaOdds(w, phase) ?? -Infinity) > ((best && ideaOdds(best, phase)) ?? -Infinity) ? w : best),
        undefined,
      );

/** What expires first goes first (no deadline last); within one day, the effect ranking. */
export function orderByDeadline(todos: readonly Todo[]): Todo[] {
  return [...todos].sort((a, b) => {
    if (a.deadlineDay !== b.deadlineDay) {
      if (a.deadlineDay === null) return 1;
      if (b.deadlineDay === null) return -1;
      return a.deadlineDay < b.deadlineDay ? -1 : 1;
    }
    return compareEffect(a, b);
  });
}

type LeagueRef = { league_key: string; league_id?: string | null; name: string | null | undefined };

const sleeperUrlOf = (l: LeagueRef): string | null => (l.league_id ? sleeperLeagueUrl(l.league_id) : null);
type Deadlines = { lineup: string | null; waiver: string | null };

const hrefFor = (page: "lineup" | "moves", leagueKey: string) => `/${page}?league=${encodeURIComponent(leagueKey)}`;

/**
 * One league's to-dos: lineup and injury actions plus the best stored waiver add. Effects come from the responses as given.
 * In the playoffs the add is judged on its title change (playoff odds are fixed); an eliminated team gets no add,
 * and a finished season gets nothing.
 */
export function leagueTodos(
  league: LeagueRef,
  actions: readonly ActionRow[],
  waivers: readonly MoveIdea[],
  deadlines: Deadlines,
  phase: Phase = "season",
): Todo[] {
  if (phase === "over") return []; // the playoffs are finished: no lineup, injury or add left to act on
  const base = { leagueKey: league.league_key, leagueName: leagueName(league), sleeperUrl: sleeperUrlOf(league) };
  const fromActions = actions
    .filter((a) => a.kind !== "Waiver" && worthActing(a, a.share_better ?? null)) // the stored add below is the waiver to-do
    .map((a, i): Todo => ({
      ...base,
      id: `${league.league_key}-${i}-${a.kind}-${a.text}`,
      kind: a.kind === "Injury" ? "injury" : "lineup",
      title: actionSentence(a.text),
      detail: a.kind,
      href: hrefFor("lineup", league.league_key),
      effect: { playoffPoints: null, points: actionGain(a) },
      why: lineupWhy(a.share_better),
      deadlineDay: deadlines.lineup,
    }));
  const title = phase !== "season";
  const top = bestIdea(waivers, phase);
  const oddsOf = (w: MoveIdea) => ideaOdds(w, phase);
  const topOdds = top === undefined ? null : oddsOf(top);
  const add: Todo[] =
    top !== undefined && topOdds !== null && topOdds >= MIN_PLAYOFF_GAIN
      ? [
          {
            ...base,
            id: `${league.league_key}-waiver-${top.get}`,
            kind: "waiver",
            title: `Add ${top.get}, drop ${top.give}`,
            detail: title ? "Best free agent for your title odds" : "Best free agent for your odds",
            href: hrefFor("moves", league.league_key),
            effect: effectOf(top.playoff_delta, top.title_delta, top.delta_points, phase),
            why: waiverWhy(top.get, top.give, title),
            deadlineDay: deadlines.waiver,
          },
        ]
      : [];
  return [...fromActions, ...add];
}

/** In the deadline week only: the best stored trade idea, if it clears the same gain bar as an add. */
export function tradeDeadlineTodos(
  league: LeagueRef,
  trades: readonly MoveIdea[],
  state: DeadlineWeekState,
  deadlineWeek: number | null,
  deadlineDay: string | null,
  phase: Phase = "season",
): Todo[] {
  const top = state === "closing" ? bestIdea(trades, phase) : undefined;
  const odds = top === undefined ? null : ideaOdds(top, phase);
  if (top === undefined || odds === null || odds < MIN_PLAYOFF_GAIN) return [];
  const title = phase !== "season";
  return [
    {
      leagueKey: league.league_key,
      leagueName: leagueName(league),
      sleeperUrl: sleeperUrlOf(league),
      id: `${league.league_key}-trade-${top.give}-${top.get}`,
      kind: "trade",
      title: `Trade deadline: ${top.give} for ${top.get}`,
      detail: `Trades close after week ${deadlineWeek}`,
      href: `${hrefFor("moves", league.league_key)}&view=trades`,
      effect: effectOf(top.playoff_delta, top.title_delta, top.delta_points, phase),
      why: tradeWhy(top.give, top.get, title),
      deadlineDay,
    },
  ];
}

/** Lineup holes and IR moves as to-dos; the deadline is the lineup deadline (next kickoff). */
export function holeTodos(league: LeagueRef, holes: readonly HoleRow[], lineupDeadline: string | null, phase: Phase = "season"): Todo[] {
  if (isDone(phase)) return []; // an eliminated team or a finished season has no lineup to cover
  return holes.map((h, i): Todo => {
    const base = {
      leagueKey: league.league_key,
      leagueName: leagueName(league),
      sleeperUrl: sleeperUrlOf(league),
      id: `${league.league_key}-hole-${i}-${h.kind}-${h.slot}`,
      href: hrefFor("lineup", league.league_key),
      effect: { playoffPoints: null, points: null },
      deadlineDay: lineupDeadline,
    };
    if (h.kind === "ir_move") {
      return { ...base, kind: "ir", title: `Move ${h.player_name} to IR to open a roster spot`, detail: "Roster" };
    }
    const reason = h.player_name ? `${h.player_name} ${HOLE_REASON[h.kind]}` : "the slot is empty";
    return {
      ...base,
      kind: "cover",
      title: `No ${h.slot} this week: ${reason}`,
      detail: "Lineup hole",
      fillIns: h.fill_ins.map((f) => `Add ${f.full_name} (${PTS(f.projection)} pts)${f.drop_name ? `, drop ${f.drop_name}` : ""}`),
    };
  });
}
