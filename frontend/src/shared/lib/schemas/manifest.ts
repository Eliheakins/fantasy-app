import { z } from "zod";

// A plain Parquet file name: nothing that could point outside the data folder (mirrors the backend).
const fileNameSchema = z.string().regex(/^[\w.-]+\.parquet$/);

export const manifestSeasonSchema = z.object({
  season: z.number().int(),
  path: fileNameSchema,
  rows: z.number().int(),
  max_week: z.number().int().nullable(),
  has_participation: z.boolean(),
});

const fileEntrySchema = z.object({ path: fileNameSchema, rows: z.number().int() });

/** Mirrors `backend/schemas/manifest.py`; the build writes it as `manifest.json` in the data folder. */
export const manifestSchema = z.object({
  schema_version: z.literal(1),
  built_at: z.string(),
  nflreadpy_version: z.string(),
  seasons: z.array(manifestSeasonSchema),
  player_index: fileEntrySchema.nullable(),
  /** Tier-1 table (one row per player per game). Older manifests lack the key. */
  player_game: fileEntrySchema.nullable().default(null),
});

export type Manifest = z.infer<typeof manifestSchema>;
