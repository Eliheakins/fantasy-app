import { FILTER_CHIP_GROUPS } from "@/shared/config/queryBuilderOptions";
import { STAT_DEFINITIONS } from "@/shared/config/statDictionary";

export interface IntentCatalogStat {
  id: string;
  label: string;
  category: string;
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
export function buildIntentCatalog(): IntentCatalog {
  return {
    stats: STAT_DEFINITIONS.map((s) => ({ id: s.id, label: s.label, category: s.category })),
    filters: FILTER_CHIP_GROUPS.flatMap((g) =>
      g.options.map((o) => ({ id: o.id, label: o.label, group: g.label })),
    ),
  };
}
