/**
 * Who a ranking may list, by position and rookie season, from the player index (one row per player:
 * position, the latest season seen and years of experience then). A rookie in season S is a player
 * whose latest season minus his years of experience is S.
 */
import type { ColumnSource, ColumnStore } from "./columns";
import type { PlayerSet, StatQueryParams } from "./statQuery";

/** The players that fit the position and rookie filters, or null when neither is on. */
export async function playersFitting(
  params: StatQueryParams,
  rookieSeason: number | null,
  store: ColumnStore,
  signal?: AbortSignal,
): Promise<Set<string> | null> {
  const position = params.position ?? null;
  const rookie = params.rookie === true;
  if (!position && !rookie) {
    return null;
  }
  if (!params.playerIndex) {
    throw new Error("The player index is not built, so players cannot be filtered by position or rookie season.");
  }
  const table = await store.table([params.playerIndex as ColumnSource], ["gsis_id", "position", "season", "years_exp"], signal);
  const { gsis_id: ids, position: positions, season, years_exp: experience } = table.cols;
  const fits = new Set<string>();
  for (let i = 0; i < table.rowCount; i++) {
    const id = ids![i];
    if (typeof id !== "string" || (position && positions![i] !== position)) continue;
    if (rookie && Number(season![i]) - Number(experience![i]) !== rookieSeason) continue;
    fits.add(id);
  }
  return fits;
}

/** A player set narrowed to `fits`: a set to keep becomes their overlap, a set to leave out is taken out of `fits`. */
export function narrowPlayerSet(set: PlayerSet | null | undefined, fits: ReadonlySet<string>): PlayerSet {
  if (!set) {
    return { ids: [...fits], exclude: false };
  }
  const listed = new Set(set.ids);
  return { ids: [...fits].filter((id) => listed.has(id) !== set.exclude), exclude: false };
}
