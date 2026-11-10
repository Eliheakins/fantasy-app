import type { components } from "@/api/schema";
import { actionGain, actionSentence, worthActing } from "@/features/thisweek/leagues/logic";
import type { ActionRow } from "@/features/thisweek/leagues/logic";
import { compareEffect, type Effect, MIN_PLAYOFF_GAIN } from "@/features/effects/effect";
import { type EffectWhy, lineupWhy, waiverWhy } from "@/features/effects/explain";

type MoveIdea = components["schemas"]["MoveIdeaRow"];

type TodoKind = "waiver" | "lineup" | "injury";
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
};

const PERCENT = 100;

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

type LeagueRef = { league_key: string; name: string | null | undefined };
type Deadlines = { lineup: string | null; waiver: string | null };

const hrefFor = (page: "lineup" | "moves", leagueKey: string) => `/${page}?league=${encodeURIComponent(leagueKey)}`;

/** One league's to-dos: lineup and injury actions plus the best stored waiver add. Effects come from the responses as given. */
export function leagueTodos(league: LeagueRef, actions: readonly ActionRow[], waivers: readonly MoveIdea[], deadlines: Deadlines): Todo[] {
  const leagueName = league.name?.trim() || league.league_key;
  const base = { leagueKey: league.league_key, leagueName };
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
  const top = waivers.reduce<MoveIdea | undefined>(
    (best, w) => ((w.playoff_delta ?? -Infinity) > (best?.playoff_delta ?? -Infinity) ? w : best),
    undefined,
  );
  const add: Todo[] =
    top !== undefined && top.playoff_delta !== null && top.playoff_delta >= MIN_PLAYOFF_GAIN
      ? [
          {
            ...base,
            id: `${league.league_key}-waiver-${top.get}`,
            kind: "waiver",
            title: `Add ${top.get}, drop ${top.give}`,
            detail: "Best free agent for your odds",
            href: hrefFor("moves", league.league_key),
            effect: { playoffPoints: top.playoff_delta * PERCENT, points: top.delta_points },
            why: waiverWhy(top.get, top.give),
            deadlineDay: deadlines.waiver,
          },
        ]
      : [];
  return [...fromActions, ...add];
}
