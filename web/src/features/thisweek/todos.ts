import type { components } from "@/api/schema";
import { actionGain, actionSentence, worthActing } from "@/features/home/logic";
import type { ActionRow } from "@/features/home/logic";

type MoveIdea = components["schemas"]["MoveIdeaRow"];

export type TodoKind = "waiver" | "lineup" | "injury";
/** playoffPoints: change in playoff odds, % points. points: fantasy points. Either may be missing. */
export type Effect = { playoffPoints: number | null; points: number | null };
export type Todo = {
  id: string;
  leagueKey: string;
  leagueName: string;
  kind: TodoKind;
  title: string;
  detail: string;
  href: string;
  effect: Effect;
  /** New York calendar day the to-do stops being possible; null when not known. */
  deadlineDay: string | null;
};

/** A stored add under this (0.5 playoff points) is inside the noise; same bar as the Do this now action. */
export const MIN_PLAYOFF_GAIN = 0.005;
const PERCENT = 100;

/** 0: has a playoff-odds effect, 1: only fantasy points, 2: no number. Units are never converted. */
function tier(e: Effect): number {
  if (e.playoffPoints !== null) return 0;
  return e.points !== null ? 1 : 2;
}

function compareEffect(a: { effect: Effect }, b: { effect: Effect }): number {
  const ta = tier(a.effect);
  const tb = tier(b.effect);
  if (ta !== tb) return ta - tb;
  if (ta === 0) return (b.effect.playoffPoints ?? 0) - (a.effect.playoffPoints ?? 0);
  if (ta === 1) return (b.effect.points ?? 0) - (a.effect.points ?? 0);
  return 0;
}

/** Biggest effect first. Array.sort is stable, so ties keep their order; the input is not changed. */
export const rankTodos = <T extends { effect: Effect }>(todos: readonly T[]): T[] => [...todos].sort(compareEffect);

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
export function leagueTodos(
  league: LeagueRef,
  actions: readonly ActionRow[],
  waivers: readonly MoveIdea[],
  deadlines: Deadlines,
): Todo[] {
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
      deadlineDay: deadlines.lineup,
    }));
  const top = waivers.reduce<MoveIdea | undefined>(
    (best, w) => ((w.playoff_delta ?? -Infinity) > (best?.playoff_delta ?? -Infinity) ? w : best),
    undefined,
  );
  const add: Todo[] =
    top !== undefined && top.playoff_delta !== null && top.playoff_delta >= MIN_PLAYOFF_GAIN
      ? [{
          ...base,
          id: `${league.league_key}-waiver-${top.get}`,
          kind: "waiver",
          title: `Add ${top.get}, drop ${top.give}`,
          detail: "Best free agent for your odds",
          href: hrefFor("moves", league.league_key),
          effect: { playoffPoints: top.playoff_delta * PERCENT, points: top.delta_points },
          deadlineDay: deadlines.waiver,
        }]
      : [];
  return [...fromActions, ...add];
}
