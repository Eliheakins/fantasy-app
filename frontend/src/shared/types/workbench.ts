/**
 * Player row shape returned by FastAPI `/search` and `/player/{id}` (aligned with roster index).
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
 * Normalized result from `runQuery` for the UI.
 */
export interface QueryResult {
  /** Result rows as plain objects (column name → value). */
  rows: Record<string, unknown>[];
  /** Column names in order. */
  columns: string[];
}
