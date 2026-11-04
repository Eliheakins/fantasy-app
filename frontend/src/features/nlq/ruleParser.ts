/**
 * A deterministic first pass at turning a question into stats, filters and a granularity. It only
 * answers when it understands every word; anything else is handed back so the model can try. A wrong
 * answer given with confidence is the failure to avoid, so an unrecognised word means "not sure",
 * never "ignore it".
 */
import {
  CHIP_COMBO_PHRASES,
  CHIP_PHRASES,
  type FilterChipGroup,
} from "@/shared/config/queryBuilderOptions";
import { getStatById, type PlayerRole, STAT_DEFINITIONS } from "@/shared/config/statDictionary";
import { MAX_SELECTED_STATS } from "@/shared/lib/queryUrl";
import type { QueryIntent } from "@/shared/lib/schemas/nlqIntent";
import type { GranularityMode } from "@/shared/types/queryBuilder";

import { type PlayerMatch, tokenize } from "./resolvePlayers";

export interface RuleContext {
  /** Players already found in the question (their words are not part of the stat wording). */
  matches: readonly PlayerMatch[];
  /** Seasons the data has. */
  seasons: readonly number[];
  chipGroups: readonly FilterChipGroup[];
}

export type RuleResult =
  | { status: "resolved"; intent: QueryIntent }
  /** A question the data cannot answer, said with certainty (a season it does not have). */
  | { status: "unsupported"; reason: string }
  /** Understood in part; the wording leaves a real choice open. `unrecognized` lists words it could not place. */
  | { status: "ambiguous"; reason: string; unrecognized?: string[] }
  | { status: "unknown"; reason: string };

type Piece =
  | { kind: "stat"; id: string }
  | { kind: "chips"; ids: readonly string[] }
  | { kind: "granularity"; value: GranularityMode };

interface Phrase {
  words: string[];
  piece: Piece;
}

/** Words that carry no meaning for the query. Anything else left over makes the parser unsure. */
const FILLER = new Set([
  "a", "an", "the", "in", "on", "at", "of", "for", "and", "vs", "versus", "compare", "what", "whats",
  "was", "were", "is", "are", "how", "many", "much", "did", "do", "does", "had", "has", "have", "his",
  "their", "during", "season", "me", "show", "tell", "give", "get", "got", "s",
]);

const GENERIC_WORDS: Readonly<Record<string, "yards" | "touchdowns">> = {
  yards: "yards",
  yard: "yards",
  yds: "yards",
  touchdowns: "touchdowns",
  touchdown: "touchdowns",
  tds: "touchdowns",
  td: "touchdowns",
};

const ROLE_BY_POSITION: Readonly<Record<string, PlayerRole>> = {
  QB: "passer",
  RB: "rusher",
  FB: "rusher",
  WR: "receiver",
  TE: "receiver",
};

/** The stat a bare "yards" or "touchdowns" means for each role; a receiver has no touchdown stat. */
const GENERIC_STAT: Readonly<Record<PlayerRole, Readonly<Record<"yards" | "touchdowns", string | null>>>> = {
  passer: { yards: "pass_yards", touchdowns: "pass_tds" },
  rusher: { yards: "rush_yards", touchdowns: "rush_tds" },
  receiver: { yards: "rec_yards", touchdowns: null },
};

const ROLE_BY_CATEGORY: Readonly<Record<string, PlayerRole>> = {
  passing: "passer",
  rushing: "rusher",
  receiving: "receiver",
};

/** A verb that settles which role a bare "yards" or "touchdowns" belongs to. */
const THROW_WORDS = new Set(["throw", "throws", "threw", "thrown"]);

const YEAR = /^(19|20)\d\d$/;

/** Words that make a number a season ("in 2019"), as opposed to a count ("reach 2000 yards"). */
const SEASON_CONTEXT = new Set(["in", "of", "during", "from", "for", "through", "to", "and", "season"]);

/** Chip groups where naming two chips means a contrast (home vs away), which one query cannot split. */
const CONTRAST_GROUPS = new Set(["location", "season_type", "game_clock", "game_state"]);

function buildPhrases(chipIds: ReadonlySet<string>): Phrase[] {
  const phrases: Phrase[] = [];
  const owners = new Map<string, string>();
  const conflicted = new Set<string>();

  for (const stat of STAT_DEFINITIONS) {
    for (const text of [...stat.aliases, stat.label]) {
      const words = tokenize(text);
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

function rolesOf(matches: readonly PlayerMatch[]): Set<PlayerRole> {
  const roles = new Set<PlayerRole>();
  for (const match of matches) {
    for (const candidate of match.candidates) {
      const role = candidate.position ? ROLE_BY_POSITION[candidate.position] : undefined;
      if (role) {
        roles.add(role);
      }
    }
  }
  return roles;
}

const unique = <T>(values: readonly T[]): T[] => [...new Set(values)];

export function parseRules(question: string, context: RuleContext): RuleResult {
  const { matches, seasons, chipGroups } = context;
  if (matches.length === 0) {
    return { status: "unknown", reason: "No player was named." };
  }

  const tokens = tokenize(question);
  const used = tokens.map(() => false);
  for (const match of matches) {
    const length = tokenize(match.phrase).length;
    for (let i = match.start; i < match.start + length && i < tokens.length; i++) {
      used[i] = true;
    }
  }

  const chipIds = new Set(chipGroups.flatMap((g) => g.options.map((o) => o.id)));
  const found: { at: number; piece: Piece }[] = [];

  for (const phrase of buildPhrases(chipIds)) {
    const { words } = phrase;
    for (let i = 0; i + words.length <= tokens.length; i++) {
      const fits = words.every((word, k) => !used[i + k] && tokens[i + k] === word);
      if (fits) {
        words.forEach((_, k) => {
          used[i + k] = true;
        });
        found.push({ at: i, piece: phrase.piece });
      }
    }
  }

  const years: { at: number; year: number }[] = [];
  let missingYear: { at: number; year: number } | undefined;
  tokens.forEach((token, at) => {
    if (used[at] || !YEAR.test(token)) {
      return;
    }
    const year = Number(token);
    const readsAsSeason =
      seasons.includes(year) || SEASON_CONTEXT.has(tokens[at - 1] ?? "") || tokens[at + 1] === "season";
    // An unrelated number is left alone, so it counts as a word the parser did not understand.
    if (!readsAsSeason) {
      return;
    }
    used[at] = true;
    if (seasons.includes(year)) {
      years.push({ at, year });
    } else {
      missingYear ??= { at, year };
    }
  });
  if (missingYear) {
    const first = Math.min(...seasons);
    const last = Math.max(...seasons);
    return {
      status: "unsupported",
      reason: `The data covers ${first}–${last}; ${missingYear.year} isn't in it.`,
    };
  }

  const generic: { at: number; word: "yards" | "touchdowns" }[] = [];
  tokens.forEach((token, at) => {
    const word = GENERIC_WORDS[token];
    if (!used[at] && word) {
      used[at] = true;
      generic.push({ at, word });
    }
  });

  let threw = false;
  tokens.forEach((token, at) => {
    if (!used[at] && THROW_WORDS.has(token)) {
      used[at] = true;
      threw = true;
    }
  });

  const leftover = tokens.filter((token, at) => !used[at] && !FILLER.has(token));
  if (leftover.length > 0) {
    const unrecognized = unique(leftover);
    return { status: "ambiguous", reason: `I didn't understand: ${unrecognized.join(", ")}.`, unrecognized };
  }

  const statAt: { at: number; id: string }[] = found.flatMap((f) => (f.piece.kind === "stat" ? [{ at: f.at, id: f.piece.id }] : []));
  if (generic.length > 0) {
    // "passing yards and touchdowns": the named stat settles the role. Otherwise only a receiver's
    // "yards" has one reading, since quarterbacks and backs both run and throw or catch.
    const named = unique([
      ...statAt.flatMap((s) => ROLE_BY_CATEGORY[getStatById(s.id)?.category ?? ""] ?? []),
      ...(threw ? (["passer"] as const) : []),
    ]);
    const role: PlayerRole | undefined = named.length === 1 ? named[0] : undefined;
    const playerRoles = rolesOf(matches);
    const fallback = playerRoles.size === 1 ? [...playerRoles][0] : undefined;
    for (const { at, word } of generic) {
      const id = role
        ? GENERIC_STAT[role][word]
        : fallback === "receiver" && word === "yards"
          ? GENERIC_STAT.receiver.yards
          : null;
      if (!id) {
        return { status: "ambiguous", reason: `"${word}" could mean passing, rushing or receiving here.` };
      }
      statAt.push({ at, id });
    }
  }

  const statIds = unique(statAt.sort((a, b) => a.at - b.at).map((s) => s.id));
  if (statIds.length === 0) {
    return { status: "unknown", reason: "No stat I know was named." };
  }
  if (statIds.length > MAX_SELECTED_STATS) {
    return { status: "ambiguous", reason: `That names more than ${MAX_SELECTED_STATS} stats.` };
  }

  const statRoles = unique(statIds.flatMap((id) => getStatById(id)?.playerRole ?? []));
  if (matches.length > 1 && statRoles.length > 1) {
    return { status: "ambiguous", reason: "It mixes players with different kinds of stat." };
  }

  const asked = unique(found.flatMap((f) => (f.piece.kind === "granularity" ? [f.piece.value] : [])));
  if (asked.length > 1) {
    return { status: "ambiguous", reason: "It asks for more than one of total, per game and per play." };
  }
  const anyRate = statIds.some((id) => getStatById(id)?.rate_only);
  const requested = asked[0];
  if (anyRate && requested !== undefined && requested !== "per_play") {
    return { status: "ambiguous", reason: "A rate stat has no total or per-game form." };
  }

  const groupOf = new Map(chipGroups.flatMap((g) => g.options.map((o): [string, string] => [o.id, g.id])));
  const namedByGroup = new Map<string, Set<string>>();
  for (const f of found) {
    for (const id of f.piece.kind === "chips" ? f.piece.ids : []) {
      const group = groupOf.get(id);
      if (group && CONTRAST_GROUPS.has(group)) {
        namedByGroup.set(group, (namedByGroup.get(group) ?? new Set()).add(id));
      }
    }
  }
  if ([...namedByGroup.values()].some((ids) => ids.size > 1)) {
    return { status: "ambiguous", reason: "It sets two cases side by side (like home and away), which one query can't split." };
  }

  const filterAt: { at: number; id: string }[] = [
    ...found.flatMap((f) => (f.piece.kind === "chips" ? f.piece.ids.map((id) => ({ at: f.at, id })) : [])),
    ...years.map((y) => ({ at: y.at, id: `season-${y.year}` })),
  ];

  return {
    status: "resolved",
    intent: {
      stat_ids: statIds,
      filter_ids: unique(filterAt.sort((a, b) => a.at - b.at).map((f) => f.id)),
      granularity: anyRate ? "per_play" : (requested ?? "total"),
    },
  };
}
