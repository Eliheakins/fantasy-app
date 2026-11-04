import { z } from "zod";

import { type QueryIntent, queryIntentSchema } from "@/shared/lib/schemas/nlqIntent";

import type { StorageLike } from "./askLog";

/**
 * Remembers what the model answered for a question so asking it again is instant, and what the user
 * corrected it to, which wins over everything. Keys carry a signature of the stat and chip ids, so a
 * new season or stat never serves an answer built for the old catalog.
 */

export const MAX_CACHE_ENTRIES = 500;
const STORAGE_KEY = "bridge.intentCache.v1";

const cachedSchema = z.object({ intent: queryIntentSchema, source: z.enum(["model", "correction"]) });

export type CachedIntent = z.infer<typeof cachedSchema>;
export type IntentCache = Record<string, CachedIntent>;

export const normalizeQuestion = (question: string): string =>
  question
    .toLowerCase()
    .replace(/['’]s\b/g, "")
    .replace(/[^a-z0-9%]+/g, " ")
    .trim();

/** A short fingerprint of the ids the model may choose from (order does not matter). */
export function catalogSignature(catalog: { stats: { id: string }[]; filters: { id: string }[] }): string {
  const ids = [...catalog.stats.map((s) => `s:${s.id}`), ...catalog.filters.map((f) => `f:${f.id}`)].sort().join("|");
  let hash = 5381;
  for (let i = 0; i < ids.length; i++) {
    hash = ((hash << 5) + hash + ids.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(36);
}

export const cacheKey = (signature: string, question: string): string => `${signature}:${normalizeQuestion(question)}`;

export function readIntentCache(storage: StorageLike): IntentCache {
  try {
    const raw: unknown = JSON.parse(storage.getItem(STORAGE_KEY) ?? "{}");
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
      return {};
    }
    const valid = Object.entries(raw).flatMap(([key, value]) => {
      const parsed = cachedSchema.safeParse(value);
      return parsed.success ? [[key, parsed.data] as const] : [];
    });
    return Object.fromEntries(valid);
  } catch {
    return {};
  }
}

export const lookupIntent = (cache: IntentCache, key: string): CachedIntent | undefined => cache[key];

export function storeIntent(storage: StorageLike, key: string, value: CachedIntent): void {
  const cache = readIntentCache(storage);
  // A correction is the user's word; a later model answer must not undo it.
  if (cache[key]?.source === "correction" && value.source === "model") {
    return;
  }
  const { [key]: _replaced, ...others } = cache;
  const entries = Object.entries({ ...others, [key]: value }).slice(-MAX_CACHE_ENTRIES);
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(entries)));
  } catch {
    // Full or blocked storage only costs the speed-up.
  }
}

export type { QueryIntent };
