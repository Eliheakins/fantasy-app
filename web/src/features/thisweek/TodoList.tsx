import { Link } from "react-router-dom";
import { Delta, ExplainDelta, NOISE_PERCENT } from "@/viz";
import type { EffectWhy } from "./explain";
import type { Effect, Todo } from "./todos";
import { dayLabel } from "./weekLogic";

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

export const deadlineText = (todo: Todo): string | null => (todo.deadlineDay === null ? null : `by ${dayLabel(todo.deadlineDay)}`);

/** The to-dos of every league, in the order given (see useTodos), each with where to act. */
export function TodoList({ todos }: { todos: readonly Todo[] }) {
  if (todos.length === 0) return <p className="text-body">Nothing needs doing in either league right now.</p>;
  return (
    <ol className="divide-y divide-panel-line">
      {todos.map((t, i) => (
        <li key={t.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3 first:pt-0 last:pb-0">
          <span aria-hidden className="w-5 text-caption font-semibold text-muted tabular-nums">{i + 1}</span>
          <div className="min-w-0 flex-1">
            <Link to={t.href} className="inline-flex min-h-[44px] items-center font-semibold underline-offset-2 hover:underline">
              {t.title}
            </Link>
            <div className="flex flex-wrap items-center gap-x-2 text-caption text-muted">
              <span className="rounded border border-line px-1.5 py-0.5 text-ink">{t.leagueName}</span>
              <span>{t.detail}</span>
              {deadlineText(t) && <span>{deadlineText(t)}</span>}
            </div>
          </div>
          <EffectText todo={t} />
        </li>
      ))}
    </ol>
  );
}
