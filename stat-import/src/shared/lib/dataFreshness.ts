import type { FilterChipGroup } from "@/shared/config/queryBuilderOptions";
import type { Manifest } from "@/shared/lib/schemas/manifest";

/** How current the data is, as "2026 week 8" (mirrors `Manifest.data_through` in the backend). */
export function dataThrough(manifest: Manifest | null): string | null {
  const latest = manifest?.seasons.at(-1);
  if (!latest) {
    return null;
  }
  return latest.max_week === null ? String(latest.season) : `${latest.season} week ${latest.max_week}`;
}

/** Chip groups whose columns come from participation data, which is published after a season ends. */
const PARTICIPATION_GROUPS = new Set(["offense_personnel", "participation_box", "pass_rush_ct"]);

/**
 * Seasons a participation filter cannot match because they have no participation data yet, or null
 * when nothing is affected. Without a season filter the query covers every season.
 */
export function participationGap(args: {
  manifest: Manifest | null;
  filters: readonly string[];
  chipGroups: readonly FilterChipGroup[];
}): { seasons: number[]; chips: string[] } | null {
  const { manifest, filters, chipGroups } = args;
  if (!manifest) {
    return null;
  }
  const participationChips = new Set(
    chipGroups.filter((g) => PARTICIPATION_GROUPS.has(g.id)).flatMap((g) => g.options.map((o) => o.id)),
  );
  const chips = filters.filter((id) => participationChips.has(id));
  if (chips.length === 0) {
    return null;
  }

  const chosen = filters.flatMap((id) => {
    const match = /^season-(\d+)$/.exec(id);
    return match ? [Number(match[1])] : [];
  });
  const covered = chosen.length > 0 ? chosen : manifest.seasons.map((s) => s.season);
  const seasons = manifest.seasons
    .filter((s) => !s.has_participation && covered.includes(s.season))
    .map((s) => s.season);
  return seasons.length > 0 ? { seasons, chips } : null;
}
