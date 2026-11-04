import { z } from "zod";

export const queryIntentSchema = z.object({
  stat_ids: z.array(z.string()).min(1),
  filter_ids: z.array(z.string()),
  granularity: z.enum(["total", "per_game", "per_play"]),
});

export type QueryIntent = z.infer<typeof queryIntentSchema>;

/** What `/nlq/intent` returns: a query to run, or why the question can't be answered. */
export const intentOutcomeSchema = z.discriminatedUnion("outcome", [
  z.object({ outcome: z.literal("query"), intent: queryIntentSchema }),
  z.object({ outcome: z.literal("unsupported"), reason: z.string().min(1) }),
]);

export type IntentOutcome = z.infer<typeof intentOutcomeSchema>;
