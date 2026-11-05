import { EffectText, deadlineText } from "./TodoList";
import { useTodos } from "./useTodos";

/** The page's answer sentence: the first thing to do, in which league, with its effect. */
export function Answer() {
  const { pending, todos, leaguesError } = useTodos();
  const top = todos[0];
  if (leaguesError !== null) return <>The leagues did not load, so there is no answer yet.</>;
  if (pending) return <>Reading both leagues…</>;
  if (!top) return <>Nothing needs doing in either league right now.</>;
  return (
    <>
      First: {top.title} <span className="text-muted">({top.leagueName}{deadlineText(top) ? `, ${deadlineText(top)}` : ""})</span>{" "}
      <EffectText todo={top} />
    </>
  );
}
