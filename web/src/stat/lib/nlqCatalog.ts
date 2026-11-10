import { STAT_DEFINITIONS } from "@/stat/config/statDictionary";
import { buildFilterChipGroups, CODE_READ_GROUP_IDS } from "@/stat/config/queryBuilderOptions";

interface IntentCatalogStat {
  id: string;
  label: string;
  category: string;
  aliases: string[];
}

interface IntentCatalogFilter {
  id: string;
  label: string;
  group: string;
}

export interface IntentCatalog {
  stats: IntentCatalogStat[];
  filters: IntentCatalogFilter[];
}

/** The ids the model may choose from; sent with every ask so the backend never owns a second copy. */
export function buildIntentCatalog(seasons: readonly number[]): IntentCatalog {
  return {
    stats: STAT_DEFINITIONS.filter((s) => !s.hidden).map((s) => ({
      id: s.id,
      label: s.label,
      category: s.category,
      aliases: s.aliases,
    })),
    // Weeks and opponents are read in code (CODE_READ_GROUP_IDS), so the model never sees them.
    filters: buildFilterChipGroups(seasons)
      .filter((g) => !CODE_READ_GROUP_IDS.has(g.id))
      .flatMap((g) => g.options.map((o) => ({ id: o.id, label: o.label, group: g.label }))),
  };
}
