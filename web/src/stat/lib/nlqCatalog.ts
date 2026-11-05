import { STAT_DEFINITIONS } from "@/stat/config/statDictionary";
import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";

export interface IntentCatalogStat {
  id: string;
  label: string;
  category: string;
  aliases: string[];
}

export interface IntentCatalogFilter {
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
    stats: STAT_DEFINITIONS.map((s) => ({
      id: s.id,
      label: s.label,
      category: s.category,
      aliases: s.aliases,
    })),
    filters: buildFilterChipGroups(seasons).flatMap((g) => g.options.map((o) => ({ id: o.id, label: o.label, group: g.label }))),
  };
}
