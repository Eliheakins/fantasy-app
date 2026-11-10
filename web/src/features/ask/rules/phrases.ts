import { CHIP_COMBO_PHRASES, CHIP_PHRASES } from "@/stat/config/queryBuilderOptions";
import { STAT_DEFINITIONS } from "@/stat/config/statDictionary";
import type { GranularityMode } from "@/stat/types/queryBuilder";

import { tokenize } from "../resolvePlayers";
import type { WordMask } from "./types";
import { GAME_PART_PREFIXES, wordsOf } from "./vocab";

type Piece = { kind: "stat"; id: string } | { kind: "chips"; ids: readonly string[] } | { kind: "granularity"; value: GranularityMode };

interface Phrase {
  words: string[];
  piece: Piece;
}

/** A phrase found in the question: the tokens it covers and what it means. */
export interface Found {
  at: number;
  end: number;
  piece: Piece;
}

function buildPhrases(chipIds: ReadonlySet<string>): Phrase[] {
  const phrases: Phrase[] = [];
  const owners = new Map<string, string>();
  const conflicted = new Set<string>();

  for (const stat of STAT_DEFINITIONS.filter((s) => !s.hidden)) {
    for (const text of [...stat.aliases, stat.label]) {
      const words = wordsOf(text);
      const key = words.join(" ");
      if (key === "") {
        continue;
      }
      const owner = owners.get(key);
      if (owner !== undefined && owner !== stat.id) {
        conflicted.add(key);
      }
      if (owner === undefined) {
        owners.set(key, stat.id);
        phrases.push({ words, piece: { kind: "stat", id: stat.id } });
      }
    }
  }

  for (const [id, texts] of Object.entries(CHIP_PHRASES)) {
    if (chipIds.has(id)) {
      texts.forEach((text) => phrases.push({ words: tokenize(text), piece: { kind: "chips", ids: [id] } }));
    }
  }
  for (const [text, ids] of Object.entries(CHIP_COMBO_PHRASES)) {
    if (ids.every((id) => chipIds.has(id))) {
      phrases.push({ words: tokenize(text), piece: { kind: "chips", ids } });
    }
  }
  phrases.push(
    { words: ["per", "game"], piece: { kind: "granularity", value: "per_game" } },
    { words: ["per", "play"], piece: { kind: "granularity", value: "per_play" } },
    { words: ["total"], piece: { kind: "granularity", value: "total" } },
  );

  // A phrase two stats share is ambiguous by construction; drop it rather than pick one.
  return phrases
    .filter((p) => !(p.piece.kind === "stat" && conflicted.has(p.words.join(" "))))
    .sort((a, b) => b.words.length - a.words.length);
}

/** Matches stat, chip and granularity phrases (longest first) over the words not yet read, and marks them read. */
export function findPhrases(tokens: readonly string[], used: WordMask, chipIds: ReadonlySet<string>): Found[] {
  const found: Found[] = [];
  for (const phrase of buildPhrases(chipIds)) {
    const { words } = phrase;
    for (let i = 0; i + words.length <= tokens.length; i++) {
      const fits = words.every((word, k) => !used[i + k] && tokens[i + k] === word);
      if (fits) {
        words.forEach((_, k) => {
          used[i + k] = true;
        });
        found.push({ at: i, end: i + words.length, piece: phrase.piece });
      }
    }
  }
  return found;
}

/** "first half of the season" is not the first half of a game: a part-of-game chip followed by "of". */
export const namesPartOfSomething = (found: readonly Found[], tokens: readonly string[]): boolean =>
  found.some(
    (f) =>
      f.piece.kind === "chips" &&
      f.piece.ids.some((id) => GAME_PART_PREFIXES.some((prefix) => id.startsWith(prefix))) &&
      tokens[f.end] === "of",
  );
