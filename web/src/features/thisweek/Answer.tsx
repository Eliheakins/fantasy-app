import { useHeld } from "@/lib/useHeld";
import { EffectText } from "@/features/effects/EffectText";
import { deadlineText } from "./TodoList";
import { useTodos } from "./useTodos";

/** The page's answer sentence: the first thing to do, in which league, with its effect. */
export function Answer() {
  const { pending, todos, leaguesError } = useTodos();
  const top = todos[0];
  const sentence =
    leaguesError !== null ? <>The leagues did not load, so there is no answer yet.</>
    : pending ? <>Reading both leagues…</>
    : !top ? <>Nothing needs doing in either league right now.</>
    : (
      <>
        First: {top.title} <span className="text-muted">({top.leagueName}{deadlineText(top) ? `, ${deadlineText(top)}` : ""})</span>{" "}
        <EffectText todo={top} inline />
      </>
    );
  // a refetch must not unmount the number the reader has open
  return <>{useHeld(sentence, pending && leaguesError === null && todos.length > 0, "week")}</>;
}
