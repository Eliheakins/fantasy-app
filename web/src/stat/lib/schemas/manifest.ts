import { z } from "zod";

// A plain Parquet file name: nothing that could point outside the data folder (mirrors the backend).
const fileNameSchema = z.string().regex(/^[\w.-]+\.parquet$/);

const manifestSeasonSchema = z.object({
  season: z.number().int(),
  path: fileNameSchema,
  rows: z.number().int(),
  max_week: z.number().int().nullable(),
  has_participation: z.boolean(),
});

const fileEntrySchema = z.object({ path: fileNameSchema, rows: z.number().int() });
const jsonFileEntrySchema = z.object({ path: z.string().regex(/^[\w.-]+\.json$/), rows: z.number().int() });

/** Mirrors `backend/schemas/manifest.py`; the build writes it as `manifest.json` in the data folder. */
export const manifestSchema = z.object({
  schema_version: z.literal(1),
  built_at: z.string(),
  nflreadpy_version: z.string(),
  seasons: z.array(manifestSeasonSchema),
  player_index: fileEntrySchema.nullable(),
  /** Tier-1 table (one row per player per game). Older manifests lack the key. */
  player_game: fileEntrySchema.nullable().default(null),
  /** Static player list (`players.json`) the browser searches and matches names against. */
  players: jsonFileEntrySchema.nullable().default(null),
});

export type Manifest = z.infer<typeof manifestSchema>;
