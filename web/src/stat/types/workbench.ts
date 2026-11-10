/**
 * Player row shape read from the static `players.json` (aligned with the roster index).
 */
export interface NFLPlayer {
  gsis_id: string;
  full_name: string | null;
  position: string | null;
  team: string | null;
  headshot_url: string | null;
  birth_date?: string | null;
  years_exp?: number | null;
}

/**
 * Result of a stat query, as the UI renders it.
 */
export interface QueryResult {
  /** Result rows as plain objects (column name → value). */
  rows: Record<string, unknown>[];
  /** Column names in order. */
  columns: string[];
  /** Things the reader should know about these rows, such as a filter that could not apply. */
  notices?: string[];
}
