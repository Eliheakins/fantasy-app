/**
 * Metric configuration for The Bridge: each entry defines `base_sql` (unqualified play columns)
 * and `rate_only` (locks granularity to the expression as written — no SUM(col) expansion).
 */
export type StatCategory =
  | "passing"
  | "rushing"
  | "receiving"
  | "efficiency"
  | "ngs_passing"
  | "ngs_receiving"
  | "ngs_rushing";

export type PlayerRole = "passer" | "rusher" | "receiver";

export type PlayTypeScope = "pass" | "run" | "all";

export interface StatDefinition {
  id: string;
  label: string;
  /** Short subtitle when no `help` tooltip, or extra context alongside help. */
  description?: string;
  /** Shown in a ? tooltip (hover/focus). Prefer this over duplicating `description`. */
  help?: string;
  category: StatCategory;
  playerRole: PlayerRole;
  playType: PlayTypeScope;
  /**
   * Aggregate SQL over filtered play rows. Use raw column names (no `main.`); the builder qualifies them.
   * For `rate_only: false`, if this is exactly `SUM(single_column)`, Total / Per play / Per game are derived.
   */
  base_sql: string;
  /** If true, the expression is used as-is (typically a rate); Total/Per game toggles are disabled in UI. */
  rate_only: boolean;
  /** Table header hint for percentage-style metrics. */
  percent_format?: boolean;
}

export const STAT_CATEGORY_ORDER: StatCategory[] = [
  "passing",
  "rushing",
  "receiving",
  "efficiency",
  "ngs_passing",
  "ngs_receiving",
  "ngs_rushing",
];

export const STAT_CATEGORY_LABELS: Record<StatCategory, string> = {
  passing: "Passing",
  rushing: "Rushing",
  receiving: "Receiving",
  efficiency: "Efficiency (analytics)",
  ngs_passing: "NGS · Passing",
  ngs_receiving: "NGS · Receiving",
  ngs_rushing: "NGS · Rushing",
};

export const STAT_DEFINITIONS: StatDefinition[] = [
  // --- Passing (passer / pass) — custom rates + volume ---------------------------------
  {
    id: "pass_any_a",
    label: "ANY/A",
    help:
      "Adjusted net yards per attempt: rewards TDs (+20×) and penalizes INTs (−45×), divided by dropbacks (pass plays counted + sacks). Higher is better.",
    category: "passing",
    playerRole: "passer",
    playType: "pass",
    base_sql:
      "(SUM(yards_gained) + (20 * SUM(pass_touchdown)) - (45 * SUM(interception))) / NULLIF((COUNT(*) + SUM(sack)), 0)",
    rate_only: true,
  },
  {
    id: "pass_sack_rate",
    label: "Sack rate",
    help: "Percentage of dropbacks that end in a sack. Denominator is pass plays in the sample plus sack plays (COUNT(*) + SUM(sack)).",
    category: "passing",
    playerRole: "passer",
    playType: "pass",
    base_sql: "SUM(sack) / NULLIF((COUNT(*) + SUM(sack)), 0) * 100",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "pass_p2s",
    label: "P2S%",
    help: "Pressure-to-sack rate: sacks divided by QB hits. High values mean hits often become sacks; undefined if SUM(qb_hit) is 0.",
    category: "passing",
    playerRole: "passer",
    playType: "pass",
    base_sql: "SUM(sack) / NULLIF(SUM(qb_hit), 0) * 100",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "pass_adot",
    label: "ADOT",
    help: "Average depth of target (air yards): mean air yards on pass attempts in the filter. Does not measure completed depth only.",
    category: "passing",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(air_yards)",
    rate_only: true,
  },
  {
    id: "pass_yards",
    label: "Pass yards",
    category: "passing",
    playerRole: "passer",
    playType: "pass",
    base_sql: "SUM(yards_gained)",
    rate_only: false,
  },
  {
    id: "pass_tds",
    label: "Pass TDs",
    category: "passing",
    playerRole: "passer",
    playType: "pass",
    base_sql: "SUM(pass_touchdown)",
    rate_only: false,
  },
  {
    id: "cmp_pct",
    label: "Cmp %",
    help: "Completion percentage on pass plays in the sample (mean of the completion flag × 100).",
    category: "passing",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(complete_pass) * 100",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "int_rate",
    label: "INT rate",
    help: "Interceptions per pass play in the sample, as a percentage (mean of INT flag × 100).",
    category: "passing",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(interception) * 100",
    rate_only: true,
    percent_format: true,
  },
  // --- Receiving (receiver / pass) ------------------------------------------------------
  {
    id: "rec_catch_rate",
    label: "Catch rate",
    help: "Catches divided by receiver-targeted pass plays in the filter (COUNT of rows). Each row is one play with this player as receiver.",
    category: "receiving",
    playerRole: "receiver",
    playType: "pass",
    base_sql: "SUM(complete_pass) / NULLIF(CAST(COUNT(*) AS DOUBLE), 0) * 100",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "rec_yac_share",
    label: "YAC share %",
    help: "Total yards after catch divided by total play yards on those targets—how much of receiving production came after the catch.",
    category: "receiving",
    playerRole: "receiver",
    playType: "pass",
    base_sql: "SUM(yards_after_catch) / NULLIF(SUM(yards_gained), 0) * 100",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "rec_explosive",
    label: "Explosive play rate",
    help: "Share of pass plays (as targeted receiver) where yards gained was 20 or more.",
    category: "receiving",
    playerRole: "receiver",
    playType: "pass",
    base_sql: "AVG(CASE WHEN yards_gained >= 20 THEN 1 ELSE 0 END) * 100",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "rec_receptions",
    label: "Receptions",
    category: "receiving",
    playerRole: "receiver",
    playType: "pass",
    base_sql: "SUM(complete_pass)",
    rate_only: false,
  },
  {
    id: "rec_yards",
    label: "Rec yards",
    category: "receiving",
    playerRole: "receiver",
    playType: "pass",
    base_sql: "SUM(yards_gained)",
    rate_only: false,
  },
  {
    id: "rec_yac",
    label: "YAC",
    category: "receiving",
    playerRole: "receiver",
    playType: "pass",
    base_sql: "SUM(yards_after_catch)",
    rate_only: false,
  },
  // --- Rushing (rusher / run) -----------------------------------------------------------
  {
    id: "rush_yac_share",
    label: "YAC share %",
    help: "YAC divided by rush yards on carries—often near 100% when all rush yards are credited as YAC on the ballcarrier row.",
    category: "rushing",
    playerRole: "rusher",
    playType: "run",
    base_sql: "SUM(yards_after_catch) / NULLIF(SUM(yards_gained), 0) * 100",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "rush_explosive",
    label: "Explosive play rate",
    help: "Share of rush plays where yards gained was 20 or more.",
    category: "rushing",
    playerRole: "rusher",
    playType: "run",
    base_sql: "AVG(CASE WHEN yards_gained >= 20 THEN 1 ELSE 0 END) * 100",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "rush_yards",
    label: "Rush yards",
    category: "rushing",
    playerRole: "rusher",
    playType: "run",
    base_sql: "SUM(yards_gained)",
    rate_only: false,
  },
  {
    id: "rush_tds",
    label: "Rush TDs",
    category: "rushing",
    playerRole: "rusher",
    playType: "run",
    base_sql: "SUM(rush_touchdown)",
    rate_only: false,
  },
  {
    id: "ypc",
    label: "YPC",
    help: "Yards per carry: average yards gained on run plays in the filter.",
    category: "rushing",
    playerRole: "rusher",
    playType: "run",
    base_sql: "AVG(yards_gained)",
    rate_only: true,
  },
  // --- Efficiency (passer / pass) -------------------------------------------------------
  {
    id: "eff_epa",
    label: "EPA/Play",
    help: "Expected Points Added: average EPA per pass play for the passer. Positive means the offense gained more expected points than before the play.",
    category: "efficiency",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(epa)",
    rate_only: true,
  },
  {
    id: "eff_success",
    label: "Success rate",
    help: "Share of pass plays classified as successful (nflverse success flag), scaled to 0–100%. Typically gains that meet down-and-distance expectations.",
    category: "efficiency",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(success) * 100",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "eff_cpoe",
    label: "CPOE",
    help: "Completion Percentage Over Expected: average difference between actual completion and model-based completion probability (nflverse cpoe), in percentage points.",
    category: "efficiency",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(cpoe)",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "eff_wpa",
    label: "WPA",
    help: "Win Probability Added summed over pass plays as passer. Total / per play / per game change how this aggregate is scaled in the UI.",
    category: "efficiency",
    playerRole: "passer",
    playType: "pass",
    base_sql: "SUM(wpa)",
    rate_only: false,
  },
  {
    id: "eff_first_down",
    label: "1st down rate",
    help: "Share of pass plays that gained a first down (or scored), as a percentage.",
    category: "efficiency",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(first_down) * 100",
    rate_only: true,
    percent_format: true,
  },
  {
    id: "eff_qb_epa",
    label: "QB EPA",
    help: "EPA attributed to the QB on pass plays (nflverse qb_epa). Totals or averages depend on granularity.",
    category: "efficiency",
    playerRole: "passer",
    playType: "pass",
    base_sql: "SUM(qb_epa)",
    rate_only: false,
  },
  {
    id: "eff_xpass",
    label: "Expected pass",
    help: "Model-estimated probability the play would be a pass (nflverse xpass), averaged over pass plays in the filter.",
    category: "efficiency",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(xpass)",
    rate_only: true,
  },
  {
    id: "eff_xyac_epa",
    label: "xYAC EPA",
    help: "Expected yards-after-catch EPA component (nflverse xyac_epa), averaged on pass plays—how much YAC exceeded or fell short of expectation.",
    category: "efficiency",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(xyac_epa)",
    rate_only: true,
  },
  {
    id: "ctx_wpa_rush",
    label: "WPA",
    help: "Win Probability Added summed on run plays where this player is the rusher. Granularity changes sum vs average vs per active game.",
    category: "efficiency",
    playerRole: "rusher",
    playType: "run",
    base_sql: "SUM(wpa)",
    rate_only: false,
  },
  {
    id: "ctx_vwpa_pass",
    label: "Vegas WPA",
    help: "Win probability added vs closing spread / Vegas-implied probabilities (nflverse vegas_wpa), summed as passer on pass plays.",
    category: "efficiency",
    playerRole: "passer",
    playType: "pass",
    base_sql: "SUM(vegas_wpa)",
    rate_only: false,
  },
  {
    id: "ctx_vwpa_rush",
    label: "Vegas WPA",
    help: "Vegas WPA summed on run plays as the ballcarrier.",
    category: "efficiency",
    playerRole: "rusher",
    playType: "run",
    base_sql: "SUM(vegas_wpa)",
    rate_only: false,
  },
  // --- NGS -----------------------------------------------------------------------------
  {
    id: "ngs_p_time_throw",
    label: "Time to throw",
    help: "Next Gen Stats: average seconds from snap to release on pass plays (weekly value repeated on each play row).",
    category: "ngs_passing",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(avg_time_to_throw)",
    rate_only: true,
  },
  {
    id: "ngs_p_intended_air",
    label: "Intended air yards",
    help: "NGS weekly average intended air yards for the passer, averaged across plays in your filter.",
    category: "ngs_passing",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(avg_intended_air_yards)",
    rate_only: true,
  },
  {
    id: "ngs_p_rating",
    label: "Passer rating",
    help: "NGS weekly passer rating for the QB, averaged across pass plays (same value within a week until play-level NGS differs).",
    category: "ngs_passing",
    playerRole: "passer",
    playType: "pass",
    base_sql: "AVG(passer_rating)",
    rate_only: true,
  },
  {
    id: "ngs_r_sep",
    label: "Separation",
    help: "NGS: average yards of separation at catch or incompletion for this receiver on targets.",
    category: "ngs_receiving",
    playerRole: "receiver",
    playType: "pass",
    base_sql: "AVG(avg_separation)",
    rate_only: true,
  },
  {
    id: "ngs_r_cushion",
    label: "Cushion",
    help: "NGS: average cushion (yards from nearest defender at snap) for this receiver on targets.",
    category: "ngs_receiving",
    playerRole: "receiver",
    playType: "pass",
    base_sql: "AVG(avg_cushion)",
    rate_only: true,
  },
  {
    id: "ngs_r_xyac",
    label: "Expected YAC",
    help: "NGS model: average expected yards after catch given spacing, speed, and defenders in space.",
    category: "ngs_receiving",
    playerRole: "receiver",
    playType: "pass",
    base_sql: "AVG(avg_expected_yac)",
    rate_only: true,
  },
  {
    id: "ngs_u_tlos",
    label: "Time to LOS",
    help: "NGS: average time (seconds) for the ballcarrier to reach the line of scrimmage on runs.",
    category: "ngs_rushing",
    playerRole: "rusher",
    playType: "run",
    base_sql: "AVG(avg_time_to_los)",
    rate_only: true,
  },
  {
    id: "ngs_u_exp_yards",
    label: "Expected rush yards",
    help: "NGS expected rush yards (xRY) from tracking/model, averaged on this player’s rush plays.",
    category: "ngs_rushing",
    playerRole: "rusher",
    playType: "run",
    base_sql: "AVG(expected_run_yards)",
    rate_only: true,
  },
  {
    id: "ngs_u_eff",
    label: "Rush efficiency",
    help: "NGS rush efficiency: total distance traveled per rushing yard gained (lower often means more north/south).",
    category: "ngs_rushing",
    playerRole: "rusher",
    playType: "run",
    base_sql: "AVG(efficiency)",
    rate_only: true,
  },
];

export function getStatById(id: string | null): StatDefinition | undefined {
  if (!id) {
    return undefined;
  }
  return STAT_DEFINITIONS.find((s) => s.id === id);
}

export function getStatsByCategory(category: StatCategory): StatDefinition[] {
  return STAT_DEFINITIONS.filter((s) => s.category === category);
}

export function playerColumnForRole(role: PlayerRole): "passer_player_id" | "rusher_player_id" | "receiver_player_id" {
  switch (role) {
    case "passer":
      return "passer_player_id";
    case "rusher":
      return "rusher_player_id";
    case "receiver":
      return "receiver_player_id";
    default:
      return "passer_player_id";
  }
}

