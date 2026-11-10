import { Callout } from "@/components/Callout";
import { participationGap } from "@/stat/lib/dataFreshness";
import { useFilterChipGroups } from "@/stat/react/filterChipGroups";
import { useQueryState } from "@/stat/react/useQueryState";
import { useManifest } from "@/stat/react/manifest";

/**
 * Personnel, box-count and pass-rusher filters need participation data, which is published after a
 * season ends. Those seasons return nothing for such filters; say so instead of showing an empty table.
 */
export function ParticipationNotice() {
  const { state } = useQueryState();
  const { manifest } = useManifest();
  const chipGroups = useFilterChipGroups();

  const gap = participationGap({ manifest, filters: state.filters, chipGroups });
  if (!gap) {
    return null;
  }
  return (
    <Callout variant="warn">
      Personnel, box and pass-rusher filters need participation data, which is not published yet for {gap.seasons.join(", ")}. Those seasons
      return no plays with these filters on.
    </Callout>
  );
}
