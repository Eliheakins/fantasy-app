export type GranularityMode = "total" | "per_game" | "per_play";

export const GRANULARITY_LABELS: Record<GranularityMode, string> = {
  total: "Total",
  per_game: "Per game",
  per_play: "Per play",
};

/** One row per player and season, per player and week (within its season), or per player at home and away. */
export type Split = "season" | "week" | "location";

/** A team's own plays (offense) or its opponents' plays against it (defense). */
export type Side = "offense" | "defense";
