import type { PlayerMatch } from "../resolvePlayers";
import { resolvePlayers } from "../resolvePlayers";
import { dropTeamNames, resolveTeams } from "../resolveTeams";
import type { AskInput } from "./types";

const memo = new WeakMap<AskInput, PlayerMatch[]>();

/** The players a question names, team names dropped; computed once per ask for the rules and model paths. */
export function matchesFor(input: AskInput): PlayerMatch[] {
  const known = memo.get(input);
  if (known) return known;
  const matches = dropTeamNames(resolvePlayers(input.question, input.dictionary), resolveTeams(input.question));
  memo.set(input, matches);
  return matches;
}
