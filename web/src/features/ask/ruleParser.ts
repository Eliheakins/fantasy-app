/**
 * A deterministic first pass at turning a question into stats, filters and a granularity. It only
 * answers when it understands every word; anything else is handed back so the model can try. A wrong
 * answer given with confidence is the failure to avoid, so an unrecognised word means "not sure",
 * never "ignore it".
 *
 * `parseRules` runs the stages in `rules/` in order. Each returns a typed partial or settles the
 * question early (`Stage`): entities, structure (names, side, split), filters (phrases, time, years),
 * stat words, stats, settings, result.
 */
import { readEntities } from "./rules/entities";
import { readFilters } from "./rules/filters";
import { buildResult } from "./rules/result";
import { readSettings } from "./rules/settings";
import { chooseStats, readStatWords } from "./rules/stats";
import { claimStructure } from "./rules/structure";
import type { RuleContext, RuleResult } from "./rules/types";

export type { Leaderboard } from "./ranking";
export { asksRanking, teamsAsked } from "./rules/entities";
export { splitAsked } from "./rules/split";
export type { RuleContext, RuleResult } from "./rules/types";
export { MAIN_ROLE } from "./rules/vocab";

export function parseRules(question: string, context: RuleContext): RuleResult {
  const entities = readEntities(question, context);
  if (!entities.ok) {
    return entities.result;
  }
  const structure = claimStructure(entities.value);
  if (!structure.ok) {
    return structure.result;
  }
  const { used, side, split } = structure.value;
  const filters = readFilters(question, context, entities.value, used);
  if (!filters.ok) {
    return filters.result;
  }
  const words = readStatWords(entities.value, filters.value, used);
  if (!words.ok) {
    return words.result;
  }
  const statIds = chooseStats(entities.value, filters.value, words.value);
  if (!statIds.ok) {
    return statIds.result;
  }
  const granularity = readSettings(statIds.value, filters.value.found, context.chipGroups, split);
  if (!granularity.ok) {
    return granularity.result;
  }
  return buildResult(entities.value, filters.value, split, side, statIds.value, granularity.value);
}
