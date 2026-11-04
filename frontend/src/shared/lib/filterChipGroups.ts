import { useMemo } from "react";

import { buildFilterChipGroups, type FilterChipGroup } from "@/shared/config/queryBuilderOptions";
import { useManifestStore } from "@/stores/useManifestStore";

/** The chip groups for the seasons currently in the data. For code that runs outside React. */
export function getFilterChipGroups(): FilterChipGroup[] {
  return buildFilterChipGroups(useManifestStore.getState().seasons);
}

/** The same groups for components; re-renders when the manifest loads. */
export function useFilterChipGroups(): FilterChipGroup[] {
  const seasons = useManifestStore((s) => s.seasons);
  return useMemo(() => buildFilterChipGroups(seasons), [seasons]);
}
