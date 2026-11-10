export type GranularityMode = "total" | "per_game" | "per_play";

/** One row per player and season, per player and week (within its season), or per player at home and away. */
export type Split = "season" | "week" | "location";

/** A team's own plays (offense) or its opponents' plays against it (defense). */
export type Side = "offense" | "defense";
