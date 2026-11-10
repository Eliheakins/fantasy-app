import { z } from "zod";

export const queryIntentSchema = z.object({
  stat_ids: z.array(z.string()).min(1),
  filter_ids: z.array(z.string()),
  granularity: z.enum(["total", "per_game", "per_play"]),
  /** The model read a ranking ("who leads"); a question with no player is then a leaderboard. */
  ranking: z.boolean().optional(),
});

export type QueryIntent = z.infer<typeof queryIntentSchema>;

/** What `/nlq/intent` returns: a query to run, or why the question can't be answered. */
export const intentOutcomeSchema = z.discriminatedUnion("outcome", [
  z.object({ outcome: z.literal("query"), intent: queryIntentSchema }),
  z.object({ outcome: z.literal("unsupported"), reason: z.string().min(1).max(300) }),
]);

export type IntentOutcome = z.infer<typeof intentOutcomeSchema>;

// Compile-time pin to the generated backend types: a pydantic change breaks `tsc` here.
type Api = import("@/api/schema").components["schemas"];
// Strict identity: an added optional field or an optional/required flip is not equal.
type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;
type ApiIntent = Api["QueryIntent"];
// filter_ids has a pydantic default, so the generated type has it optional and zod's output has it
// required. Pin that exact gap: if the backend makes it required (or drops it) this line breaks.
const _filterIdsOptionalInApi: {} extends Pick<ApiIntent, "filter_ids"> ? true : false = true;
// ranking has a pydantic default (the API always sends it); zod leaves it optional, since the rules
// and saved intents have none.
const _rankingOptionalHere: {} extends Pick<QueryIntent, "ranking"> ? true : false = true;
const _intentMatchesApi: Equal<Required<QueryIntent>, Required<ApiIntent>> = true;
const _outcomeMatchesApi: Equal<IntentOutcome, { outcome: "query"; intent: QueryIntent } | Api["UnsupportedOutcome"]> = true;

void _rankingOptionalHere;
void _filterIdsOptionalInApi;
void _intentMatchesApi;
void _outcomeMatchesApi;
