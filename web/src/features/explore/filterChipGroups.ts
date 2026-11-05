import { useMemo } from "react";

import { useManifest } from "@/features/explore/manifest";
import { buildFilterChipGroups, type FilterChipGroup } from "@/stat/config/queryBuilderOptions";

/** The chip groups for the seasons currently in the data. */
export function useFilterChipGroups(): FilterChipGroup[] {
  const { seasons } = useManifest();
  return useMemo(() => buildFilterChipGroups(seasons), [seasons]);
}
