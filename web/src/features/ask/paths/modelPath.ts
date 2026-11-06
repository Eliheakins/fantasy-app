import { getStatById, type PlayerRole } from "@/stat/config/statDictionary";
import { type IntentOutcome, type QueryIntent, requestIntent } from "@/stat/lib/nlqApi";
import { buildIntentCatalog } from "@/stat/lib/nlqCatalog";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import { browserStorage } from "../askLogStore";
import { cacheKey, catalogSignature, lookupIntent, readIntentCache, storeIntent } from "../intentCache";
import { type Interpretation, interpretQuestion } from "../interpretQuestion";
import { narrowByRoles, type PlayerMatch, pickCandidate } from "../resolvePlayers";
import { matchesFor } from "./matches";
import { showIntent, showModelRanking } from "./queryStates";
import type { AskInput, AskPath } from "./types";

/** The cache key for a question under the catalog as it is now. */
export const keyFor = (seasons: readonly number[], question: string) =>
  cacheKey(catalogSignature(buildIntentCatalog(seasons)), question);

function rolesOf(intent: QueryIntent): PlayerRole[] {
  const roles = intent.stat_ids.flatMap((id) => {
    const stat = getStatById(id);
    // A league stat belongs to no position: it must not narrow who "Josh Allen" can be.
    return stat && stat.source === "pbp" ? [stat.playerRole] : [];
  });
  return [...new Set(roles)];
}

/**
 * Reads a question: a correction the user saved wins, then the rules, then the model, whose answers
 * are remembered so asking again costs nothing.
 */
async function interpret(input: AskInput, matches: PlayerMatch[]): Promise<Interpretation> {
  const { question, seasons, chipGroups, signal } = input;
  const storage = browserStorage();
  const key = keyFor(seasons, question);
  const cached = storage ? lookupIntent(readIntentCache(storage), key) : undefined;
  if (cached?.source === "correction") {
    return { kind: "intent", intent: cached.intent, path: "saved" };
  }
  const askModel = async (q: string): Promise<IntentOutcome> => {
    if (cached?.source === "model") {
      return { outcome: "query", intent: cached.intent };
    }
    const outcome = await requestIntent(q, seasons, signal);
    if (storage && !signal.aborted && outcome.outcome === "query") {
      storeIntent(storage, key, { intent: outcome.intent, source: "model" });
    }
    return outcome;
  };
  return interpretQuestion({ question, matches, seasons, chipGroups, maxWeeks: input.maxWeeks, askModel });
}

/** The catch-all: a question no other path took; with no player named it can only be a ranking. */
export const modelPath: AskPath<Interpretation> = {
  id: "model",
  read: (input) => interpret(input, matchesFor(input)),
  answer: (interpretation, input, actions) => {
    const { question } = input;
    if (interpretation.kind === "message") {
      actions.fail(question, "none", interpretation.text);
      return;
    }
    const { intent, path } = interpretation;
    const unrecognized = interpretation.unrecognized ?? [];
    const scope = { seasons: input.seasons, maxWeeks: input.maxWeeks };
    if (matchesFor(input).length === 0) {
      showModelRanking(intent, question, path, unrecognized, actions, scope);
      return;
    }
    const roles = rolesOf(intent);
    const sure: PlayerDictionaryRow[] = [];
    const unsure: PlayerMatch[] = [];
    for (const match of matchesFor(input)) {
      const pick = pickCandidate(match, roles);
      if (pick) {
        sure.push(pick);
      } else {
        unsure.push({ ...match, candidates: narrowByRoles(match.candidates, roles) });
      }
    }
    if (unsure.length > 0) {
      actions.choose(sure, unsure, (players, asked) =>
        showIntent(players, intent, asked, path, unrecognized, actions, scope),
      );
      return;
    }
    showIntent(sure, intent, question, path, unrecognized, actions, scope);
  },
};
