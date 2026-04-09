import { z } from "zod";

export const hubDictionaryRowSchema = z.object({
  bridge_id: z.number(),
  display_name: z.string(),
  search_key: z.string(),
  nfl_id: z.string().nullable(),
  cfb_id: z.string().nullable(),
});

export const hubDictionarySchema = z.array(hubDictionaryRowSchema);

export type HubDictionaryRowParsed = z.infer<typeof hubDictionaryRowSchema>;
