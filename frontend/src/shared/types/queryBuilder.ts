export type GranularityMode = "total" | "per_game" | "per_play";

/** One row per player and season, or per player and week (within its season). */
export type Split = "season" | "week";

/** A team's own plays (offense) or its opponents' plays against it (defense). */
export type Side = "offense" | "defense";
