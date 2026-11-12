import type { Player } from "@/stat/lib/schemas/players";

/** A `players.json` row; the name is null for a pinned id not (yet) in the list. */
export type NFLPlayer = Omit<Player, "full_name"> & { full_name: string | null };

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
