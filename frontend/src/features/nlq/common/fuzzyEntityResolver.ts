import fuzzysort from "fuzzysort";

export type FuzzyResolveReason = "ok" | "no_candidate_phrases" | "no_confident_match";

export interface FuzzyResolveResult<TOut> {
  reason: FuzzyResolveReason;
  phrase: string;
  bestScore: number;
  results: TOut[];
}

export interface FuzzyResolveOptions<TDictRow> {
  /** Field name containing a normalized search key (e.g. full_name lowercased). */
  key: keyof TDictRow & string;
  /** Hard cutoff; fuzzysort scores are <= 0 (closer to 0 is better). */
  scoreCutoff: number;
  /** Stopwords used to avoid generating generic phrases. */
  stopwords: Set<string>;
  /** Maximum tokens from question to consider. */
  maxTokens?: number;
  /** Maximum n-gram phrases to evaluate. */
  maxGrams?: number;
  /** N-gram sizes to generate. */
  ngramSizes?: ReadonlyArray<number>;
  /** fuzzysort result limit per phrase. */
  perPhraseLimit?: number;
}

const DEFAULT_MAX_TOKENS = 24;
const DEFAULT_MAX_GRAMS = 60;
const DEFAULT_NGRAM_SIZES = [2, 3, 4];
const DEFAULT_PER_PHRASE_LIMIT = 12;

function tokenizeQuestion(raw: string): string[] {
  return raw
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .filter(Boolean);
}

function buildPhrases<TDictRow>(tokens: string[], opts: FuzzyResolveOptions<TDictRow>): string[] {
  const maxTokens = opts.maxTokens ?? DEFAULT_MAX_TOKENS;
  const maxGrams = opts.maxGrams ?? DEFAULT_MAX_GRAMS;
  const ngramSizes = opts.ngramSizes ?? DEFAULT_NGRAM_SIZES;

  const usable = tokens.slice(0, maxTokens);
  const phrases: string[] = [];
  for (let i = 0; i < usable.length; i++) {
    for (const n of ngramSizes) {
      if (i + n > usable.length) continue;
      const gram = usable.slice(i, i + n);
      if (gram.every((t) => opts.stopwords.has(t))) continue;
      phrases.push(gram.join(" "));
      if (phrases.length >= maxGrams) break;
    }
    if (phrases.length >= maxGrams) break;
  }
  return phrases;
}

/**
 * Resolve entities by generating 2–4 token phrases from a question, fuzzysorting each phrase against a dictionary,
 * and returning the top hits from the best-scoring phrase (subject to a hard score cutoff).
 */
export function resolveWithNgramFuzzysort<TDictRow, TOut>(
  question: string,
  dict: TDictRow[],
  mapRow: (row: TDictRow) => TOut,
  dedupeKey: (out: TOut) => string | number,
  opts: FuzzyResolveOptions<TDictRow>,
  maxOutputs = 8,
): FuzzyResolveResult<TOut> {
  const raw = question.trim();
  if (!raw || dict.length === 0) {
    return { reason: "no_candidate_phrases", phrase: "", bestScore: Number.NEGATIVE_INFINITY, results: [] };
  }

  const tokens = tokenizeQuestion(raw);
  const phrases = buildPhrases(tokens, opts);
  if (phrases.length === 0) {
    return { reason: "no_candidate_phrases", phrase: "", bestScore: Number.NEGATIVE_INFINITY, results: [] };
  }

  const perPhraseLimit = opts.perPhraseLimit ?? DEFAULT_PER_PHRASE_LIMIT;
  let bestPhrase = "";
  let bestScore = Number.NEGATIVE_INFINITY;
  let bestResults: Array<{ obj: TDictRow; score: number }> = [];

  for (const p of phrases) {
    const r = fuzzysort.go(p, dict as unknown as TDictRow[], {
      key: opts.key,
      limit: perPhraseLimit,
      threshold: Number.NEGATIVE_INFINITY,
    }) as unknown as Array<{ obj: TDictRow; score: number }>;
    if (r.length === 0) continue;
    if (r[0].score > bestScore) {
      bestScore = r[0].score;
      bestPhrase = p;
      bestResults = r;
    }
  }

  if (!bestPhrase || bestScore < opts.scoreCutoff) {
    return { reason: "no_confident_match", phrase: bestPhrase, bestScore, results: [] };
  }

  const seen = new Set<string | number>();
  const out: TOut[] = [];
  for (const r of bestResults) {
    const mapped = mapRow(r.obj);
    const k = dedupeKey(mapped);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(mapped);
    if (out.length >= maxOutputs) break;
  }

  return { reason: "ok", phrase: bestPhrase, bestScore, results: out };
}

