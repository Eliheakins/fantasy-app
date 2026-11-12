import type { components } from "@/api/schema";

export type WaiverRow = components["schemas"]["WaiverRow"];
export type StashData = components["schemas"]["StashData"];
export type StashRow = components["schemas"]["StashRow"];
export type StreamerRow = components["schemas"]["StreamerRow"];
export type PlayerWeekRow = components["schemas"]["PlayerWeekRow"];

export const ADDS_CAPTION = "Free agents ranked by extra points over the rest of the season. Select a player to see the next four weeks.";
export const ADDS_METHOD =
  "Extra points are the expected points over the rest of the season above what the roster would have anyway. Every slot can always be filled by a stand-in free agent (bye weeks, injuries and weak starters included), so a backup at a position with plenty of free agents adds almost nothing, and the drop is whoever costs least. Playoff and title changes re-run the season simulation with the move made, on the same random draws as the unchanged roster. The title change carries a Monte Carlo error of up to the value in the Title error column, so title changes smaller than that are noise (shown as ~). Injured players are scaled by their status. Sleeper adds is how many users added the player in the latest trending pull, a rough sign of who else will bid. Not every claim goes through: 67 of 105 waiver claims in these two leagues this season succeeded (64%), and the rate did not rise or fall with the player's market value, so no claim chance is shown per player.";
export const STREAM_CAPTION = "Projected points over the next three weeks; a bye week counts as zero. Treat small gaps as noise.";
export const STREAM_METHOD =
  "The projection is a regression on recent form and the game's implied total; kickers also use the spread, home field, the team's recent offense, the kicker's recent kick volume and the opposing defense's points allowed. Against a plain league average it has about 5% to 7% lower error for defenses and about 2% for kickers.";

export type Rank = "ros" | "playoffs";
export type PlayoffWeeks = { first: number; last: number } | null;

export const ADDS_CAPTION_PLAYOFFS =
  "Free agents ranked by extra points over the league's playoff weeks only; playoff and title changes are unchanged. Select a player to see the next four weeks.";
export const STREAM_PLAYOFF_NOTE =
  "Playoff weeks column: far-week kicker and defense numbers rest on team strength and byes, and are untested.";

/** "playoff weeks 15 to 17" for the status line and caption; the weeks are omitted until the league is known. */
export const playoffLabel = (w: PlayoffWeeks): string => (w ? `playoff weeks ${w.first} to ${w.last}` : "playoff weeks");

export const STASH_CAPTION =
  "Injured free agents and your own injured players, ranked by projected points in the playoff weeks. First projected week is when our projections resume, not a medical estimate.";
export const STASH_ANCHOR = "stash-for-playoffs";
