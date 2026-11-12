import { Link } from "react-router-dom";
import { EffectText } from "@/features/effects/EffectText";
import { ExternalLink } from "@/components/ExternalLink";
import { FILL_IN_LABEL, NO_FILL_IN, type Todo } from "./todos";
import { dayLabel } from "./weekLogic";

export const deadlineText = (todo: Todo): string | null => (todo.deadlineDay === null ? null : `by ${dayLabel(todo.deadlineDay)}`);

/** The to-dos of every league, in the order given (see useTodos), each with where to act. */
export function TodoList({ todos }: { todos: readonly Todo[] }) {
  if (todos.length === 0) return <p className="text-body">Nothing needs doing in either league right now.</p>;
  return (
    <ol className="divide-y divide-panel-line">
      {todos.map((t, i) => (
        <li key={t.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3 first:pt-0 last:pb-0">
          <span aria-hidden className="w-5 text-caption font-semibold text-muted tabular-nums">
            {i + 1}
          </span>
          <div className="min-w-0 flex-1">
            <Link to={t.href} className="inline-flex min-h-[44px] items-center font-semibold underline-offset-2 hover:underline">
              {t.title}
            </Link>
            <div className="flex flex-wrap items-center gap-x-2 text-caption text-muted">
              <span className="rounded border border-line px-1.5 py-0.5 text-ink">{t.leagueName}</span>
              <span>{t.detail}</span>
              {deadlineText(t) && <span>{deadlineText(t)}</span>}
            </div>
            {t.fillIns && (
              <div className="text-caption">
                {t.fillIns.length === 0 ? (
                  <p>{NO_FILL_IN}</p>
                ) : (
                  <>
                    <p className="text-muted">{FILL_IN_LABEL}</p>
                    <ul className="list-disc pl-5">
                      {t.fillIns.map((f) => (
                        <li key={f}>{f}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            )}
            {t.sleeperUrl && <ExternalLink href={t.sleeperUrl}>Open {t.leagueName} in Sleeper</ExternalLink>}
          </div>
          <EffectText todo={t} />
        </li>
      ))}
    </ol>
  );
}
