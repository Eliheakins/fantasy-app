/** Situational filter chips (WHERE); predicates reference unqualified column names. */
import { TEAMS } from "./teams";

export interface FilterChipOption {
  id: string;
  label: string;
  predicate: string;
}

export interface FilterChipGroup {
  id: string;
  label: string;
  description?: string;
  combine: "or" | "and";
  options: FilterChipOption[];
}

/** The last week a season can have, playoffs included (22 since 2021). */
export const MAX_WEEK = 22;

/**
 * Chip groups Ask reads in code (weeks, opponents) rather than through the model: numbers and team
 * names are read reliably by rules, and listing them would add dozens of questions to every model call.
 */
export const CODE_READ_GROUP_IDS: ReadonlySet<string> = new Set(["week_number", "opponent"]);

const GROUP_TEMPLATES: FilterChipGroup[] = [
  {
    id: "down",
    label: "Down",
    description: "Multi-select",
    combine: "or",
    options: [
      { id: "down-1", label: "1st", predicate: "down = 1" },
      { id: "down-2", label: "2nd", predicate: "down = 2" },
      { id: "down-3", label: "3rd", predicate: "down = 3" },
      { id: "down-4", label: "4th", predicate: "down = 4" },
    ],
  },
  {
    id: "ydstogo",
    label: "Distance to go",
    description: "Multi-select",
    combine: "or",
    options: [
      { id: "ytg-short", label: "Short (≤3)", predicate: "ydstogo <= 3" },
      { id: "ytg-long", label: "Long (≥8)", predicate: "ydstogo >= 8" },
    ],
  },
  {
    id: "season",
    label: "Season",
    description: "Multi-select",
    combine: "or",
    options: [], // filled from the data manifest, see buildFilterChipGroups
  },
  {
    id: "week",
    label: "Week",
    description: "Calendar week of season",
    combine: "or",
    options: [
      { id: "week-early", label: "Early (≤6)", predicate: "week <= 6" },
      { id: "week-mid", label: "Mid (7–12)", predicate: "week >= 7 AND week <= 12" },
      { id: "week-late", label: "Late (≥13)", predicate: "week >= 13" },
    ],
  },
  {
    id: "week_number",
    label: "Week number",
    description: "Single weeks; several make a range",
    combine: "or",
    options: Array.from({ length: MAX_WEEK }, (_, k) => ({ id: `wk-${k + 1}`, label: `Week ${k + 1}`, predicate: `week = ${k + 1}` })),
  },
  {
    id: "opponent",
    label: "Opponent",
    description: "The defense a player's (or team's offense's) plays came against",
    combine: "or",
    options: TEAMS.map((t) => ({ id: `opp-${t.id}`, label: `vs ${t.nickname}`, predicate: `defteam = '${t.id}'` })),
  },
  {
    id: "location",
    label: "Location",
    description: "Offense home / away",
    combine: "or",
    options: [
      { id: "loc-home", label: "Home", predicate: "posteam_type = 'home'" },
      { id: "loc-away", label: "Away", predicate: "posteam_type = 'away'" },
    ],
  },
  {
    id: "field",
    label: "Field position",
    combine: "or",
    options: [
      { id: "field-redzone", label: "Red zone", predicate: "yardline_100 <= 20" },
      { id: "yl-inside10", label: "Inside the 10", predicate: "yardline_100 <= 10" },
      { id: "yl-inside5", label: "Inside the 5 (goal line)", predicate: "yardline_100 <= 5" },
    ],
  },
  {
    id: "red_zone_flag",
    label: "Red zone (flag)",
    description: "`is_red_zone` from pipeline",
    combine: "or",
    options: [{ id: "rz-flag", label: "Red zone play", predicate: "(is_red_zone = TRUE OR is_red_zone = 1)" }],
  },
  {
    id: "goal_to_go",
    label: "Goal to go",
    combine: "or",
    options: [{ id: "gtg-yes", label: "Goal to go", predicate: "(goal_to_go = TRUE OR goal_to_go = 1)" }],
  },
  {
    id: "season_type",
    label: "Season type",
    combine: "or",
    options: [
      { id: "stype-reg", label: "Regular season", predicate: "season_type = 'REG'" },
      { id: "stype-post", label: "Playoffs", predicate: "season_type = 'POST'" },
    ],
  },
  {
    id: "quarter",
    label: "Quarter",
    description: "Multi-select",
    combine: "or",
    options: [
      { id: "qtr-1", label: "Q1", predicate: "qtr = 1" },
      { id: "qtr-2", label: "Q2", predicate: "qtr = 2" },
      { id: "qtr-3", label: "Q3", predicate: "qtr = 3" },
      { id: "qtr-4", label: "Q4", predicate: "qtr = 4" },
    ],
  },
  {
    id: "game_clock",
    label: "Game clock",
    description: "By `game_seconds_remaining`",
    combine: "or",
    options: [
      { id: "gclk-first-half", label: "1st half", predicate: "game_seconds_remaining > 1800" },
      { id: "gclk-second-half", label: "2nd half", predicate: "game_seconds_remaining <= 1800" },
    ],
  },
  {
    id: "game_state",
    label: "Game state",
    combine: "or",
    options: [
      { id: "score-leading", label: "Leading", predicate: "score_differential > 0" },
      { id: "score-trailing", label: "Trailing", predicate: "score_differential < 0" },
    ],
  },
  {
    id: "offense_personnel",
    label: "Offense personnel",
    description: "nflverse `offense_personnel` string",
    combine: "or",
    options: [
      {
        id: "pers-11",
        label: "11 (1·1·3)",
        predicate: "offense_personnel LIKE '%1 RB, 1 TE, 3 WR%'",
      },
      {
        id: "pers-12",
        label: "12 (1·2·2)",
        predicate: "offense_personnel LIKE '%1 RB, 2 TE, 2 WR%'",
      },
      {
        id: "pers-21",
        label: "21 (2·1·2)",
        predicate: "offense_personnel LIKE '%2 RB, 1 TE, 2 WR%'",
      },
      {
        id: "pers-10",
        label: "10 (0·1·4)",
        predicate: "offense_personnel LIKE '%0 RB, 1 TE, 4 WR%'",
      },
    ],
  },
  {
    id: "participation_box",
    label: "Defenders in box",
    description: "FTN participation (when present on play)",
    combine: "or",
    options: [
      { id: "dib-lte6", label: "Light box (≤6)", predicate: "defenders_in_box <= 6" },
      { id: "dib-gte7", label: "Heavy box (≥7)", predicate: "defenders_in_box >= 7" },
    ],
  },
  {
    id: "pass_rush_ct",
    label: "Pass rushers",
    combine: "or",
    options: [
      // Seasons 2023+ report 0 rushers on run plays (2021-22 leave it empty), so restrict to
      // pass plays or the chip matches nearly every run.
      {
        id: "pr-lte3",
        label: "≤3 rushers",
        predicate: "play_type = 'pass' AND number_of_pass_rushers <= 3",
      },
      { id: "pr-gte4", label: "≥4 rushers", predicate: "number_of_pass_rushers >= 4" },
    ],
  },
  {
    id: "weather",
    label: "Weather",
    combine: "or",
    options: [
      { id: "wind-gte15", label: "Windy (wind 15 mph or more)", predicate: "wind >= 15" },
      { id: "temp-lte32", label: "Cold weather (32°F or colder)", predicate: "temp <= 32" },
    ],
  },
];

function seasonOption(season: number): FilterChipOption {
  return { id: `season-${season}`, label: String(season), predicate: `season = ${season}` };
}

/** The chip groups, with one season chip for every season the data has (oldest first). */
export function buildFilterChipGroups(seasons: readonly number[]): FilterChipGroup[] {
  const years = [...new Set(seasons)].sort((a, b) => a - b);
  return GROUP_TEMPLATES.map((g) => (g.id === "season" ? { ...g, options: years.map(seasonOption) } : g)).filter(
    (g) => g.options.length > 0,
  );
}

export function getAllFilterChipIds(groups: readonly FilterChipGroup[]): string[] {
  return groups.flatMap((g) => g.options.map((o) => o.id));
}

/**
 * Everyday phrases for each chip, as the rules parser reads them: lowercase, plain words, no punctuation.
 * Season chips are not listed; the parser builds those from the years in a question. A chip with no entry
 * (the red-zone flag) cannot be reached by words, because a second chip already covers the same phrase.
 */
export const CHIP_PHRASES: Readonly<Record<string, readonly string[]>> = {
  "down-1": ["first down", "1st down"],
  "down-2": ["second down", "2nd down"],
  "down-3": ["third down", "3rd down"],
  "down-4": ["fourth down", "4th down"],
  "ytg-short": ["short yardage", "short distance"],
  "ytg-long": ["long distance"],
  "week-early": ["early season", "early in the season"],
  "week-mid": ["midseason", "mid season"],
  "week-late": ["week 13 or later", "late season", "late in the season"],
  "loc-home": ["at home", "home games", "home game", "home"],
  "loc-away": ["on the road", "road games", "road game", "away games", "away game", "away from home", "away"],
  "field-redzone": ["red zone", "redzone", "inside the 20"],
  "yl-inside10": ["inside the 10", "inside the ten", "inside 10"],
  "yl-inside5": ["inside the 5", "inside the five", "inside 5", "goal line", "goalline"],
  "gtg-yes": ["goal to go"],
  "stype-reg": ["regular season"],
  "stype-post": ["playoffs", "playoff", "postseason", "post season"],
  "qtr-1": ["first quarter", "1st quarter", "q1"],
  "qtr-2": ["second quarter", "2nd quarter", "q2"],
  "qtr-3": ["third quarter", "3rd quarter", "q3"],
  "qtr-4": ["fourth quarter", "4th quarter", "q4"],
  "gclk-first-half": ["first half", "1st half"],
  "gclk-second-half": ["second half", "2nd half"],
  "score-leading": ["when leading", "while leading", "when ahead", "while ahead"],
  "score-trailing": ["when trailing", "while trailing", "when behind", "while behind"],
  "pers-11": ["11 personnel"],
  "pers-12": ["12 personnel"],
  "pers-21": ["21 personnel"],
  "pers-10": ["10 personnel"],
  "dib-lte6": ["light box"],
  "dib-gte7": ["heavy box", "stacked box"],
  "pr-lte3": ["three or fewer rushers", "3 or fewer rushers"],
  "pr-gte4": ["four or more rushers", "4 or more rushers"],
  "wind-gte15": ["windy games", "windy", "in the wind"],
  "temp-lte32": ["cold weather", "cold games", "freezing"],
};

/** A phrase that means more than one chip at once, such as "third and long". */
export const CHIP_COMBO_PHRASES: Readonly<Record<string, readonly string[]>> = {
  "third and long": ["down-3", "ytg-long"],
  "3rd and long": ["down-3", "ytg-long"],
  "third and short": ["down-3", "ytg-short"],
  "3rd and short": ["down-3", "ytg-short"],
};
