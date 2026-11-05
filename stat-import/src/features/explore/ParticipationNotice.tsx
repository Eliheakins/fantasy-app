import { Callout } from "@/shared/components/Callout";
import { participationGap } from "@/shared/lib/dataFreshness";
import { useFilterChipGroups } from "@/shared/lib/filterChipGroups";
import { useQueryState } from "@/shared/lib/useQueryState";
import { useManifestStore } from "@/stores/useManifestStore";

/**
 * Personnel, box-count and pass-rusher filters need participation data, which is published after a
 * season ends. Those seasons return nothing for such filters; say so instead of showing an empty table.
 */
export function ParticipationNotice() {
  const { state } = useQueryState();
  const manifest = useManifestStore((s) => s.manifest);
  const chipGroups = useFilterChipGroups();

  const gap = participationGap({ manifest, filters: state.filters, chipGroups });
  if (!gap) {
    return null;
  }
  return (
    <Callout variant="warn">
      Personnel, box and pass-rusher filters need participation data, which is not published yet for{" "}
      {gap.seasons.join(", ")}. Those seasons return no plays with these filters on.
    </Callout>
  );
}
