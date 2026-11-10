import { Delta, ExplainDelta, NOISE_PERCENT } from "@/viz";
import type { Effect } from "./effect";
import type { EffectWhy } from "./explain";

function NumberDelta({ points, noise, why, row }: { points: number; noise?: number; why: string | null; row: boolean }) {
  return why === null ? <Delta points={points} noise={noise} /> : <ExplainDelta points={points} noise={noise} why={why} row={row} />;
}

/** `playoffNoise` is the playoff-odds change (points) below which it reads "~"; Moves passes its own bar. */
export function EffectText({ todo, playoffNoise = NOISE_PERCENT, inline = false }: { todo: { effect: Effect; why?: EffectWhy }; playoffNoise?: number; inline?: boolean }) {
  const { playoffPoints, points } = todo.effect;
  const { playoff, points: pointsWhy } = todo.why ?? { playoff: null, points: null };
  if (playoffPoints === null && points === null) return null;
  return (
    <span className="flex flex-wrap items-baseline gap-x-3">
      {playoffPoints !== null && (
        <span className="whitespace-nowrap"><NumberDelta points={playoffPoints} noise={playoffNoise} why={playoff} row={!inline} /> <span className="text-caption text-muted">playoff pts</span></span>
      )}
      {points !== null && (
        <span className="whitespace-nowrap"><NumberDelta points={points} why={pointsWhy} row={!inline} /> <span className="text-caption text-muted">points</span></span>
      )}
    </span>
  );
}
