import { z } from "zod";

/** Mirrors `backend/schemas/players.py`: the `players.json` the data build writes. */
const playerSchema = z.object({
  gsis_id: z.string().min(1),
  full_name: z.string().min(1),
  position: z.string().nullable().default(null),
  team: z.string().nullable().default(null),
  // Third-party addresses: anything but https is dropped rather than failing the whole list.
  headshot_url: z
    .string()
    .nullable()
    .default(null)
    .transform((url) => (url !== null && url.toLowerCase().startsWith("https://") ? url : null)),
  birth_date: z.string().nullable().default(null),
  years_exp: z.number().nullable().default(null),
});

export const playersFileSchema = z.object({
  schema_version: z.literal(1),
  players: z.array(playerSchema),
});

export type Player = z.infer<typeof playerSchema>;

/** A player as Ask matches names: a display name and a lowercase key. */
export interface PlayerDictionaryRow {
  gsis_id: string;
  display_name: string;
  search_key: string;
  position: string | null;
  team: string | null;
}
