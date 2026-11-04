import { z } from "zod";

export const manifestSeasonSchema = z.object({
  season: z.number().int(),
  path: z.string(),
  rows: z.number().int(),
  max_week: z.number().int().nullable(),
  has_participation: z.boolean(),
});

/** Mirrors `backend/schemas/manifest.py`; the build writes it as `manifest.json` in the data folder. */
export const manifestSchema = z.object({
  schema_version: z.number().int(),
  built_at: z.string(),
  nflreadpy_version: z.string(),
  seasons: z.array(manifestSeasonSchema),
  player_index: z.object({ path: z.string(), rows: z.number().int() }).nullable(),
});

export type Manifest = z.infer<typeof manifestSchema>;
