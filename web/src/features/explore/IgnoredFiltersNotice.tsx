import { Callout } from "@/components/Callout";
import { useQueryState } from "@/features/explore/useQueryState";

/** A shared link can name filters this data does not have (a season that was never built); say so. */
export function IgnoredFiltersNotice() {
  const { ignoredFilters } = useQueryState();

  if (ignoredFilters.length === 0) {
    return null;
  }
  return (
    <Callout variant="warn">
      This link names filters the data does not have, so they were not applied: {ignoredFilters.join(", ")}. The numbers
      may differ from what the sender saw.
    </Callout>
  );
}
