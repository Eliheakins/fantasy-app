import type { PlayerRole } from "@/shared/config/statDictionary";
import type { PlayerDictionaryRow } from "@/shared/lib/schemas/playerDictionary";

export interface PlayerMatch {
  phrase: string;
  /** Token index of the phrase in the question, to keep matches in reading order. */
  start: number;
  candidates: PlayerDictionaryRow[];
}

const MAX_NAME_TOKENS = 4;
const MIN_SURNAME_LENGTH = 3;
const NAME_SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv", "v"]);

/** Surnames that are also everyday words in stat questions; a bare one is not a player reference. */
const STOPWORDS = new Set([
  "the", "and", "for", "per", "vs", "versus", "with", "from", "his", "her", "their", "what", "how",
  "many", "much", "did", "does", "had", "has", "have", "got", "get", "who", "which", "when",
  "yards", "yard", "pass", "passing", "passes", "rush", "rushing", "receiving", "receptions",
  "catches", "touchdowns", "touchdown", "play", "plays", "game", "games", "season", "seasons",
  "third", "down", "downs", "quarter", "half", "zone", "playoffs", "regular", "home", "away",
  "total", "average", "compare", "career", "last", "this", "year", "best", "worst", "top", "most",
]);

/** Positions that can plausibly record each stat role; used to pick between namesakes. */
const POSITIONS_BY_ROLE: Record<PlayerRole, readonly string[]> = {
  passer: ["QB"],
  rusher: ["RB", "FB", "QB", "WR"],
  receiver: ["WR", "TE", "RB", "FB"],
};

export function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/['’.]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .split(" ")
    .filter(Boolean);
}

function stripSuffix(tokens: string[]): string[] {
  const out = [...tokens];
  while (out.length > 1 && NAME_SUFFIXES.has(out[out.length - 1]!)) {
    out.pop();
  }
  return out;
}

interface NameIndex {
  byFullName: Map<string, PlayerDictionaryRow[]>;
  bySurname: Map<string, PlayerDictionaryRow[]>;
}

const indexCache = new WeakMap<readonly PlayerDictionaryRow[], NameIndex>();

function addTo(map: Map<string, PlayerDictionaryRow[]>, key: string, row: PlayerDictionaryRow): void {
  map.set(key, [...(map.get(key) ?? []), row]);
}

function indexFor(dict: readonly PlayerDictionaryRow[]): NameIndex {
  const cached = indexCache.get(dict);
  if (cached) {
    return cached;
  }
  const index: NameIndex = { byFullName: new Map(), bySurname: new Map() };
  for (const row of dict) {
    const tokens = stripSuffix(tokenize(row.display_name));
    if (tokens.length === 0) {
      continue;
    }
    addTo(index.byFullName, tokens.join(" "), row);
    addTo(index.bySurname, tokens[tokens.length - 1]!, row);
  }
  indexCache.set(dict, index);
  return index;
}

/**
 * Finds players named in a question. A multi-word phrase must equal a full name; a single word
 * must equal a surname (so "will" never matches Will Levis). Longer phrases win, and a word is
 * used by at most one match. Namesakes come back as one match with several candidates.
 */
export function resolvePlayers(question: string, dict: readonly PlayerDictionaryRow[]): PlayerMatch[] {
  const tokens = tokenize(question);
  const index = indexFor(dict);
  const used = tokens.map(() => false);
  const found: PlayerMatch[] = [];

  for (let size = MAX_NAME_TOKENS; size >= 1; size--) {
    for (let start = 0; start + size <= tokens.length; start++) {
      if (used.slice(start, start + size).some(Boolean)) {
        continue;
      }
      const phrase = stripSuffix(tokens.slice(start, start + size));
      const word = phrase[0]!;
      if (phrase.length === 1 && (word.length < MIN_SURNAME_LENGTH || STOPWORDS.has(word))) {
        continue;
      }
      const candidates =
        phrase.length === 1 ? index.bySurname.get(word) : index.byFullName.get(phrase.join(" "));
      if (candidates) {
        used.fill(true, start, start + size);
        found.push({ phrase: phrase.join(" "), start, candidates });
      }
    }
  }

  return found.sort((a, b) => a.start - b.start);
}

/** Keep namesakes whose position fits the stats asked about; fall back to all if none fit. */
export function narrowByRoles(
  candidates: PlayerDictionaryRow[],
  roles: readonly PlayerRole[],
): PlayerDictionaryRow[] {
  if (roles.length === 0) {
    return candidates;
  }
  const allowed = new Set(roles.flatMap((r) => POSITIONS_BY_ROLE[r]));
  const fits = candidates.filter((c) => c.position !== null && allowed.has(c.position));
  return fits.length > 0 ? fits : candidates;
}

/** The single player a match refers to once roles are considered, or null if still ambiguous. */
export function pickCandidate(
  match: PlayerMatch,
  roles: readonly PlayerRole[],
): PlayerDictionaryRow | null {
  const narrowed = narrowByRoles(match.candidates, roles);
  return narrowed.length === 1 ? narrowed[0]! : null;
}
