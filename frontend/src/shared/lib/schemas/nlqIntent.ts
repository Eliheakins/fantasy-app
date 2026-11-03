import { z } from "zod";

export const queryIntentSchema = z.object({
  stat_ids: z.array(z.string()).min(1),
  filter_ids: z.array(z.string()),
  granularity: z.enum(["total", "per_game", "per_play"]),
});

export type QueryIntent = z.infer<typeof queryIntentSchema>;
