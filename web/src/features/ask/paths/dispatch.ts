import { ASK_PATHS } from "./index";
import type { AskActions, AskInput, AskPath } from "./types";

/**
 * Gives the question to each path in order; the first whose `read` matches answers it. `isStale` is
 * checked after every read, so a slow model reply cannot replace an answer the user has moved past.
 * A failing read rejects; the caller shows the message.
 */
export async function dispatchAsk(
  input: AskInput,
  actions: AskActions,
  isStale: () => boolean,
  paths: readonly AskPath[] = ASK_PATHS,
): Promise<void> {
  for (const path of paths) {
    const match = await path.read(input);
    if (isStale()) return;
    if (match === null) continue;
    path.answer(match, input, actions);
    return;
  }
}
