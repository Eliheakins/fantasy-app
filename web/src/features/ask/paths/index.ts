import { modelPath } from "./modelPath";
import { rulesPath } from "./rulesPath";
import { startSitPath } from "./startSitPath";
import { routePath } from "./routePath";
import { tradePath } from "./tradePath";
import type { AskPath } from "./types";

/** Each path reads its own match type; the list only needs `read` and `answer` to agree per path. */
const erase = <M>(path: AskPath<M>): AskPath => path as unknown as AskPath;

/** First path whose `read` returns a match answers. The model is last: it takes whatever the others leave. */
export const ASK_PATHS: readonly AskPath[] = [
  erase(startSitPath),
  erase(tradePath),
  erase(routePath),
  erase(rulesPath),
  erase(modelPath),
];
