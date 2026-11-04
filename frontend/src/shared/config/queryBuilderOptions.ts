/** Situational filter chips (WHERE); predicates reference unqualified column names. */

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

export const FILTER_CHIP_GROUPS: FilterChipGroup[] = [
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
    options: [
      { id: "season-2021", label: "2021", predicate: "season = 2021" },
      { id: "season-2022", label: "2022", predicate: "season = 2022" },
      { id: "season-2023", label: "2023", predicate: "season = 2023" },
      { id: "season-2024", label: "2024", predicate: "season = 2024" },
      { id: "season-2025", label: "2025", predicate: "season = 2025" },
    ],
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
    options: [{ id: "field-redzone", label: "Red zone", predicate: "yardline_100 <= 20" }],
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
      // Run plays carry a real 0 here, so restrict to pass plays or the chip matches nearly every run.
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
      { id: "wind-gte15", label: "Wind ≥ 15 mph", predicate: "wind >= 15" },
      { id: "temp-lte32", label: "Cold ≤ 32°F", predicate: "temp <= 32" },
    ],
  },
];

export function getAllFilterChipIds(): string[] {
  return FILTER_CHIP_GROUPS.flatMap((g) => g.options.map((o) => o.id));
}
