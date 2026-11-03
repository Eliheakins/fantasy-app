import { z } from "zod";

export const playerDictionaryRowSchema = z.object({
  gsis_id: z.string(),
  display_name: z.string(),
  search_key: z.string(),
  position: z.string().nullable(),
  team: z.string().nullable(),
});

export const playerDictionarySchema = z.array(playerDictionaryRowSchema);

export type PlayerDictionaryRow = z.infer<typeof playerDictionaryRowSchema>;
