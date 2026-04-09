import { z } from "zod";

export const unifiedNlqResponseSchema = z.object({
  track: z.enum(["telescope", "microscope_nfl", "microscope_cfb"]),
  sql: z.string(),
});

export type UnifiedNlqResponseParsed = z.infer<typeof unifiedNlqResponseSchema>;
