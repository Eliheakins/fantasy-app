import { hubDictionaryJsonUrl } from "@/shared/lib/api";
import { resolveWithNgramFuzzysort } from "@/features/nlq/common/fuzzyEntityResolver";
import { hubDictionarySchema, type HubDictionaryRowParsed } from "@/shared/lib/schemas/hubDictionary";

export type HubDictionaryRow = HubDictionaryRowParsed;

export interface ResolvedNlqEntity {
  bridge_id: number;
  display_name: string;
}

let hubDictionaryCache: HubDictionaryRow[] | null = null;

/** Fetch once per session unless `force` is true. */
export async function fetchHubDictionary(force = false): Promise<HubDictionaryRow[]> {
  if (hubDictionaryCache && !force) {
    return hubDictionaryCache;
  }
  const res = await fetch(hubDictionaryJsonUrl());
  if (!res.ok) {
    throw new Error(`hub_dictionary.json: ${res.status} ${res.statusText}`);
  }
  const raw: unknown = await res.json();
  const parsed = hubDictionarySchema.safeParse(raw);
  if (!parsed.success) {
    throw new Error(`hub_dictionary.json: invalid shape (${parsed.error.message})`);
  }
  hubDictionaryCache = parsed.data;
  return parsed.data;
}

export function clearHubDictionaryCache(): void {
  hubDictionaryCache = null;
}

/**
 * Fuzzy-match the question against `search_key` rows; return deduped bridge_ids (best scores first).
 */
export function resolveNlqEntities(question: string, dict: HubDictionaryRow[]): ResolvedNlqEntity[] {
  const stop = new Set<string>([
    "what",
    "was",
    "the",
    "average",
    "epa",
    "per",
    "play",
    "when",
    "on",
    "off",
    "field",
    "for",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "with",
    "without",
    "by",
    "from",
    "at",
    "as",
    "is",
    "are",
    "were",
    "be",
    "been",
    "top",
    "bottom",
    "best",
    "worst",
    "rank",
    "ranking",
    "leaderboard",
    "wide",
    "receiver",
    "receivers",
    "wr",
    "qb",
    "rb",
    "te",
    "season",
    "regular",
    "reg",
    "post",
    "playoffs",
    "nfl",
    "cfb",
  ]);

  const { results } = resolveWithNgramFuzzysort(
    question,
    dict,
    (row) => ({ bridge_id: row.bridge_id, display_name: row.display_name }),
    (e) => e.bridge_id,
    { key: "search_key", scoreCutoff: -175, stopwords: stop },
  );

  return results;
}
