import type { PlayerRole } from "@/stat/config/statDictionary";

import { LEADERBOARD_CUES } from "../ranking";
import { tokenize } from "../resolvePlayers";

/** Words that carry no meaning for the query. Anything else left over makes the parser unsure. */
export const FILLER = new Set([
  "a",
  "an",
  "the",
  "in",
  "on",
  "at",
  "of",
  "for",
  "and",
  "what",
  "whats",
  "was",
  "were",
  "is",
  "are",
  "how",
  "many",
  "much",
  "did",
  "do",
  "does",
  "had",
  "has",
  "have",
  "his",
  "their",
  "during",
  "me",
  "show",
  "tell",
  "give",
  "get",
  "got",
  "s",
]);

/**
 * Words that only mean "compare" between two player names ("Kelce vs Kittle"). Next to a stat, season
 * or situation they set two cases side by side, which one query cannot split, so they stay unread.
 */
export const COMPARE_WORDS = new Set(["vs", "versus", "compare"]);

export type GenericWord = "yards" | "touchdowns";

export const GENERIC_WORDS: Readonly<Record<string, GenericWord>> = {
  yards: "yards",
  yard: "yards",
  yds: "yards",
  touchdowns: "touchdowns",
  touchdown: "touchdowns",
  tds: "touchdowns",
  td: "touchdowns",
};

/** The stat roles a player in each position can have. */
export const ROLES_BY_POSITION: Readonly<Record<string, readonly PlayerRole[]>> = {
  QB: ["passer", "rusher"],
  RB: ["rusher", "receiver"],
  FB: ["rusher", "receiver"],
  WR: ["receiver", "rusher"],
  TE: ["receiver"],
};

/** The one role a position is mainly known for, used to read a bare "yards" and to pick a stat family's member. */
export const MAIN_ROLE: Readonly<Record<string, PlayerRole>> = {
  QB: "passer",
  RB: "rusher",
  FB: "rusher",
  WR: "receiver",
  TE: "receiver",
};

/** The stat a bare "yards" or "touchdowns" means for each role. */
export const GENERIC_STAT: Readonly<Record<PlayerRole, Readonly<Record<GenericWord, string | null>>>> = {
  passer: { yards: "pass_yards", touchdowns: "pass_tds" },
  rusher: { yards: "rush_yards", touchdowns: "rush_tds" },
  receiver: { yards: "rec_yards", touchdowns: "rec_tds" },
};

export const ROLE_BY_CATEGORY: Readonly<Record<string, PlayerRole>> = {
  passing: "passer",
  rushing: "rusher",
  receiving: "receiver",
};

/** Words that ask for a player's stat line rather than one stat. */
export const STAT_LINE_WORDS = new Set(["stats", "stat", "line", "statline", "numbers", "statistics"]);
/** The counting stats a stat line shows for each position (at most five, all totals). */
export const STAT_LINES: Readonly<Record<string, readonly string[]>> = {
  QB: ["pass_yards", "pass_tds", "pass_int", "rush_yards", "rush_tds"],
  RB: ["rush_att", "rush_yards", "rush_tds", "rec_receptions", "rec_yards"],
  FB: ["rush_att", "rush_yards", "rush_tds", "rec_receptions", "rec_yards"],
  WR: ["rec_tgt", "rec_receptions", "rec_yards", "rec_tds"],
  TE: ["rec_tgt", "rec_receptions", "rec_yards", "rec_tds"],
};

/** A verb that settles which role a bare "yards" or "touchdowns" belongs to. */
export const THROW_WORDS = new Set(["throw", "throws", "threw", "thrown"]);

/** Words a leaderboard question uses around its stat; read as filler only when no player is named. */
export const LEADERBOARD_WORDS = new Set([
  ...LEADERBOARD_CUES,
  "who",
  "league",
  "nfl",
  "by",
  "with",
  "among",
  "qualified",
  "players",
  "in",
]);
/** "Who had more rushing yards, Henry or Barkley": between or before two names these only set them side by side. */
export const NAMED_COMPARE_WORDS = new Set(["who", "had", "has", "more", "better", "or"]);
/** Words that make a question about teams, and that pick the side of the ball. */
export const TEAM_WORDS = new Set(["team", "teams"]);
/** "which defense", "best offenses": a side of the ball names a team question when no player is named ("allowed" alone does not). */
export const UNIT_NOUNS = new Set(["defense", "defenses", "offense", "offenses"]);
export const DEFENSE_WORDS = new Set(["allowed", "allow", "allows", "against", "forced", "defense", "defenses", "defensive"]);
export const OFFENSE_WORDS = new Set(["offense", "offenses", "offensive"]);
/** "allowed by the Chiefs", "which team": read as filler only in a team question. */
export const TEAM_FILLER = new Set(["by", "which"]);

export const YEAR = /^(19|20)\d\d$/;
/** 2020-2023, 2022–23, 2021/22: a span of seasons, which would otherwise read as two separate years. */
export const YEAR_RANGE = /\b(19|20)\d\d\s*[-–—/]\s*(\d{4}|\d{2})\b/;

/** Words that make a number a season ("in 2019"), as opposed to a count ("pass for 2000 yards"). */
export const SEASON_CONTEXT = new Set(["in", "during", "season"]);

/** Chip groups where naming two chips means a contrast (home vs away), which one query cannot split. */
export const CONTRAST_GROUPS = new Set(["location", "season_type", "game_clock", "game_state"]);

/** Chips that name a part of a game; "of the season" after them means something else. */
export const GAME_PART_PREFIXES = ["gclk-", "qtr-"];

/** Words as the parser reads them. A "%" is a word ("sack %"), not punctuation, so "sack" alone is not "sack %". */
export const wordsOf = (text: string): string[] => tokenize(text.replace(/%/g, " percent "));

export const unique = <T>(values: readonly T[]): T[] => [...new Set(values)];
