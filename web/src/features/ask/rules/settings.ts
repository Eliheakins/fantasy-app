import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import { getStatById } from "@/stat/config/statDictionary";
import type { GranularityMode } from "@/stat/types/queryBuilder";

import type { Found } from "./phrases";
import type { SplitRead } from "./split";
import { ambiguous, proceed, type Stage, stop } from "./types";
import { CONTRAST_GROUPS, unique } from "./vocab";

/** "home vs away" is a split by home and away, so its two chips are the split, not filters. */
export const splitsByLocation = (split: SplitRead): boolean => split.split === "location";

/** The granularity the words and the stats settle on, or an ambiguity when they disagree. */
function readGranularity(statIds: readonly string[], found: readonly Found[]): Stage<GranularityMode> {
  const asked = unique(found.flatMap((f) => (f.piece.kind === "granularity" ? [f.piece.value] : [])));
  if (asked.length > 1) {
    return stop(ambiguous("It asks for more than one of total, per game and per play."));
  }
  const rate = statIds.filter((id) => getStatById(id)?.rate_only);
  const requested = asked[0];
  if (rate.length > 0 && requested !== undefined && requested !== "per_play") {
    return stop(ambiguous("A rate stat has no total or per-game form."));
  }
  if (rate.length > 0 && rate.length < statIds.length && requested !== "per_play") {
    // Rates are per play, counts are totals; one setting would turn the counts into per-play values.
    return stop(ambiguous("It mixes counting stats with rates, which need different settings."));
  }
  return proceed(rate.length > 0 ? "per_play" : (requested ?? "total"));
}

/** Two chips of one contrast group (first and second half) set two cases side by side, which one query can't split. */
function checkContrasts(found: readonly Found[], chipGroups: readonly FilterChipGroup[], split: SplitRead): Stage<null> {
  const groupOf = new Map(chipGroups.flatMap((g) => g.options.map((o): [string, string] => [o.id, g.id])));
  const namedByGroup = new Map<string, Set<string>>();
  for (const f of found) {
    for (const id of f.piece.kind === "chips" ? f.piece.ids : []) {
      const group = groupOf.get(id);
      if (group && CONTRAST_GROUPS.has(group)) {
        namedByGroup.set(group, (namedByGroup.get(group) ?? new Set()).add(id));
      }
    }
  }
  const byLocation = splitsByLocation(split);
  if ([...namedByGroup].some(([group, ids]) => ids.size > 1 && !(byLocation && group === "location"))) {
    return stop(ambiguous("It sets two cases side by side (like first and second half), which one query can't split."));
  }
  return proceed(null);
}

/** Reads the granularity and checks the chips for contrasts. */
export function readSettings(
  statIds: readonly string[],
  found: readonly Found[],
  chipGroups: readonly FilterChipGroup[],
  split: SplitRead,
): Stage<GranularityMode> {
  const granularity = readGranularity(statIds, found);
  if (!granularity.ok) {
    return granularity;
  }
  const contrasts = checkContrasts(found, chipGroups, split);
  return contrasts.ok ? granularity : contrasts;
}
