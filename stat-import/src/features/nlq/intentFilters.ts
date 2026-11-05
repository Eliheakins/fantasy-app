const REGULAR_SEASON_ID = "stype-reg";
const SEASON_TYPE_IDS = [REGULAR_SEASON_ID, "stype-post"];

/**
 * Stat sites report the regular season unless asked otherwise, while the shards also hold playoff
 * games. Add the regular-season chip when the question named no season type.
 */
export function withDefaultSeasonType(filterIds: string[]): string[] {
  return filterIds.some((id) => SEASON_TYPE_IDS.includes(id)) ? filterIds : [...filterIds, REGULAR_SEASON_ID];
}
