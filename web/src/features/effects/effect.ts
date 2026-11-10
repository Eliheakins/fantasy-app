/** playoffPoints: change in playoff odds, % points. points: fantasy points. Either may be missing. */
export type Effect = { playoffPoints: number | null; points: number | null };

/** A stored add under this (0.5 playoff points) is inside the noise; same bar as the Do this now action. */
export const MIN_PLAYOFF_GAIN = 0.005;

/** 0: has a playoff-odds effect, 1: only fantasy points, 2: no number. Units are never converted. */
function tier(e: Effect): number {
  if (e.playoffPoints !== null) return 0;
  return e.points !== null ? 1 : 2;
}

export function compareEffect(a: { effect: Effect }, b: { effect: Effect }): number {
  const ta = tier(a.effect);
  const tb = tier(b.effect);
  if (ta !== tb) return ta - tb;
  if (ta === 0) return (b.effect.playoffPoints ?? 0) - (a.effect.playoffPoints ?? 0);
  if (ta === 1) return (b.effect.points ?? 0) - (a.effect.points ?? 0);
  return 0;
}

/** Biggest effect first. Array.sort is stable, so ties keep their order; the input is not changed. */
export const rankTodos = <T extends { effect: Effect }>(todos: readonly T[]): T[] => [...todos].sort(compareEffect);
