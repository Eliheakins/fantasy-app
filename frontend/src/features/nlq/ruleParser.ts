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
import { MAX_SELECTED_STATS, type QueryOrder } from "@/shared/lib/queryUrl";
import type { QueryIntent } from "@/shared/lib/schemas/nlqIntent";
import type { GranularityMode } from "@/shared/types/queryBuilder";

import { NAME_SUFFIXES, type PlayerMatch, tokenize } from "./resolvePlayers";

export interface RuleContext {
  /** Players already found in the question (their words are not part of the stat wording). */
  matches: readonly PlayerMatch[];
  /** Seasons the data has. */
  seasons: readonly number[];
  chipGroups: readonly FilterChipGroup[];
}

/** A league-wide ranking: the stat to order by, how many rows to keep, and the plays a player needs to qualify. */
export interface Leaderboard {
  order: QueryOrder;
  limit: number;
  minPlays: number;
}

export type RuleResult =
  | { status: "resolved"; intent: QueryIntent; leaderboard?: Leaderboard }
  /** A question the data cannot answer, said with certainty (a season it does not have). */
  | { status: "unsupported"; reason: string }
  /** Understood in part; the wording leaves a real choice open. `unrecognized` lists words it could not place. */
  | { status: "ambiguous"; reason: string; unrecognized?: string[] }
  | { status: "unknown"; reason: string };

type Piece =
  | { kind: "stat"; id: string }
  | { kind: "chips"; ids: readonly string[] }
  | { kind: "granularity"; value: GranularityMode }
  | { kind: "ambiguous"; reason: string };

interface Phrase {
  words: string[];
  piece: Piece;
}

/** Words that carry no meaning for the query. Anything else left over makes the parser unsure. */
const FILLER = new Set([
  "a", "an", "the", "in", "on", "at", "of", "for", "and", "what", "whats", "was", "were", "is", "are",
  "how", "many", "much", "did", "do", "does", "had", "has", "have", "his", "their", "during", "me",
  "show", "tell", "give", "get", "got", "s",
]);

/**
 * Words that only mean "compare" between two player names ("Kelce vs Kittle"). Next to a stat, season
 * or situation they set two cases side by side, which one query cannot split, so they stay unread.
 */
const COMPARE_WORDS = new Set(["vs", "versus", "compare"]);

/** Wordings the stat list maps to a rate where the question asks for a count. */
const COUNT_WORDS = new Map<string, string>([
  ["interceptions", "There is no interception count, only a rate."],
  ["picks", "There is no interception count, only a rate."],
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

/** The stat roles a player in each position can have. */
const ROLES_BY_POSITION: Readonly<Record<string, readonly PlayerRole[]>> = {
  QB: ["passer", "rusher"],
  RB: ["rusher", "receiver"],
  FB: ["rusher", "receiver"],
  WR: ["receiver", "rusher"],
  TE: ["receiver"],
};

/** The one role a position is mainly known for, used to read a bare "yards". */
const MAIN_ROLE: Readonly<Record<string, PlayerRole>> = {
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

/** Words that set which end of a ranking comes first. "best" and "worst" depend on the stat (see `better`). */
const RANK_DIRECTION = new Map<string, "desc" | "asc" | "best" | "worst">([
  ["most", "desc"],
  ["highest", "desc"],
  ["fewest", "asc"],
  ["least", "asc"],
  ["lowest", "asc"],
  ["bottom", "asc"],
  ["best", "best"],
  ["worst", "worst"],
]);
/** Words that ask for a ranking. Without one of these, a question with no player is not a leaderboard. */
const LEADERBOARD_CUES = new Set(["led", "leader", "leaders", "leading", "top", "leaderboard", ...RANK_DIRECTION.keys()]);
/** Words a leaderboard question uses around its stat; read as filler only when no player is named. */
const LEADERBOARD_WORDS = new Set([...LEADERBOARD_CUES, "who", "league", "nfl", "lead"]);
const DEFAULT_LEADERBOARD_LIMIT = 10;
const MAX_LEADERBOARD_LIMIT = 100;
/** A rate or per-game ranking needs a floor of plays, or a player with one play tops it. */
const LEADERBOARD_MIN_PLAYS = 100;

const YEAR = /^(19|20)\d\d$/;
/** 2020-2023, 2022\u201323, 2021/22: a span of seasons, which would otherwise read as two separate years. */
const YEAR_RANGE = /\b(19|20)\d\d\s*[-\u2013\u2014/]\s*(\d{4}|\d{2})\b/;

/** Words that make a number a season ("in 2019"), as opposed to a count ("pass for 2000 yards"). */
const SEASON_CONTEXT = new Set(["in", "during", "season"]);

/** Chip groups where naming two chips means a contrast (home vs away), which one query cannot split. */
const CONTRAST_GROUPS = new Set(["location", "season_type", "game_clock", "game_state"]);

/** Chips that name a part of a game; "of the season" after them means something else. */
const GAME_PART_PREFIXES = ["gclk-", "qtr-"];

/** Words as the parser reads them. A "%" is a word ("sack %"), not punctuation, so "sack" alone is not "sack %". */
const wordsOf = (text: string): string[] => tokenize(text.replace(/%/g, " percent "));

function buildPhrases(chipIds: ReadonlySet<string>): Phrase[] {
  const phrases: Phrase[] = [];
  const owners = new Map<string, string>();
  const conflicted = new Set<string>();

  for (const stat of STAT_DEFINITIONS) {
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
        const reason = COUNT_WORDS.get(key);
        phrases.push({ words, piece: reason ? { kind: "ambiguous", reason } : { kind: "stat", id: stat.id } });
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

function candidatePositions(match: PlayerMatch): string[] {
  return match.candidates.flatMap((c) => (c.position ? [c.position] : []));
}

/** The role a player is mainly known for, when all of a match's candidates agree on one. */
function mainRoles(matches: readonly PlayerMatch[]): Set<PlayerRole> {
  const roles = new Set<PlayerRole>();
  for (const match of matches) {
    for (const position of candidatePositions(match)) {
      const role = MAIN_ROLE[position];
      if (role) {
        roles.add(role);
      }
    }
  }
  return roles;
}

const unique = <T>(values: readonly T[]): T[] => [...new Set(values)];
const ambiguous = (reason: string, unrecognized?: string[]): RuleResult =>
  unrecognized ? { status: "ambiguous", reason, unrecognized } : { status: "ambiguous", reason };

export function parseRules(question: string, context: RuleContext): RuleResult {
  const { matches, seasons, chipGroups } = context;
  const tokensForCue = wordsOf(question);
  const isLeaderboard = matches.length === 0 && tokensForCue.some((t) => LEADERBOARD_CUES.has(t));
  if (matches.length === 0 && !isLeaderboard) {
    return { status: "unknown", reason: "No player was named." };
  }
  if (seasons.length === 0) {
    return { status: "unknown", reason: "The data has no seasons." };
  }
  if (YEAR_RANGE.test(question)) {
    return ambiguous("It names a range of seasons, which is read as a list of years only when each is written out.");
  }

  const tokens = wordsOf(question);
  const used = tokens.map(() => false);
  const sortedMatches = [...matches].sort((a, b) => a.start - b.start);
  for (const match of sortedMatches) {
    const length = tokenize(match.phrase).length;
    let end = match.start + length;
    // A suffix ("Jr.") was dropped from the stored phrase but is still part of the name in the question.
    while (end < tokens.length && NAME_SUFFIXES.has(tokens[end]!)) {
      end++;
    }
    for (let i = match.start; i < end && i < tokens.length; i++) {
      used[i] = true;
    }
  }
  const isName = [...used];

  // "Kelce vs Kittle" and "Compare Kelce and Kittle" are comparisons of players; anywhere else they are unread.
  tokens.forEach((token, at) => {
    if (!COMPARE_WORDS.has(token)) {
      return;
    }
    const between = token !== "compare" && isName[at - 1] && isName[at + 1];
    const leading = token === "compare" && isName[at + 1];
    if (between || leading) {
      used[at] = true;
    }
  });

  let limit = DEFAULT_LEADERBOARD_LIMIT;
  if (isLeaderboard) {
    // "top 5", "fewest 5": the number after a ranking word is the limit, not a stat or a season.
    const top = tokens.findIndex((t, at) => (t === "top" || RANK_DIRECTION.has(t)) && /^\d+$/.test(tokens[at + 1] ?? ""));
    if (top >= 0 && /^\d+$/.test(tokens[top + 1] ?? "")) {
      limit = Number(tokens[top + 1]);
      used[top + 1] = true;
      if (limit < 1 || limit > MAX_LEADERBOARD_LIMIT) {
        return ambiguous(`A leaderboard shows 1 to ${MAX_LEADERBOARD_LIMIT} rows.`);
      }
    }
  }

  const chipIds = new Set(chipGroups.flatMap((g) => g.options.map((o) => o.id)));
  const found: { at: number; end: number; piece: Piece }[] = [];

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

  const unsure = found.find((f) => f.piece.kind === "ambiguous");
  if (unsure && unsure.piece.kind === "ambiguous") {
    return ambiguous(unsure.piece.reason);
  }
  // "first half of the season" is not the first half of a game.
  const partOfSomething = found.find(
    (f) =>
      f.piece.kind === "chips" &&
      f.piece.ids.some((id) => GAME_PART_PREFIXES.some((prefix) => id.startsWith(prefix))) &&
      tokens[f.end] === "of",
  );
  if (partOfSomething) {
    return ambiguous("It names part of a game followed by 'of', which is not a part of a game.");
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
  // "the 2023 season" and "season 2023" are fine; a season with no year ("in a season") is not a filter.
  tokens.forEach((token, at) => {
    if (!used[at] && (token === "season" || token === "seasons")) {
      const nextToYear = years.some((y) => y.at === at - 1 || y.at === at + 1);
      used[at] = nextToYear;
    }
  });

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

  if (isLeaderboard) {
    tokens.forEach((token, at) => {
      used[at] ||= LEADERBOARD_WORDS.has(token);
    });
  }

  const leftover = tokens.filter((token, at) => !used[at] && !FILLER.has(token));
  if (leftover.length > 0) {
    const unrecognized = unique(leftover);
    return ambiguous(`I didn't understand: ${unrecognized.join(", ")}.`, unrecognized);
  }

  // Several players: details between their names may belong to only one of them.
  if (sortedMatches.length > 1) {
    const afterFirst = sortedMatches[0]!.start + tokenize(sortedMatches[0]!.phrase).length;
    const beforeLast = sortedMatches[sortedMatches.length - 1]!.start;
    const details = [...found.map((f) => f.at), ...years.map((y) => y.at), ...generic.map((g) => g.at)];
    if (details.some((at) => at >= afterFirst && at < beforeLast)) {
      return ambiguous("Details sit between the players' names, so it is unclear which player they belong to.");
    }
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
    const playerRoles = mainRoles(matches);
    const fallback = playerRoles.size === 1 ? [...playerRoles][0] : undefined;
    for (const { at, word } of generic) {
      // "total yards" adds up passing, rushing and receiving, which no single stat does.
      const isTotal = tokens[at - 1] === "total";
      const id = role
        ? GENERIC_STAT[role][word]
        : fallback === "receiver" && word === "yards" && !isTotal
          ? GENERIC_STAT.receiver.yards
          : null;
      if (!id) {
        return ambiguous(`"${word}" could mean passing, rushing or receiving here.`);
      }
      statAt.push({ at, id });
    }
  }

  const statIds = unique(statAt.sort((a, b) => a.at - b.at).map((s) => s.id));
  if (statIds.length === 0) {
    return { status: "unknown", reason: "No stat I know was named." };
  }
  if (statIds.length > MAX_SELECTED_STATS) {
    return ambiguous(`That names more than ${MAX_SELECTED_STATS} stats.`);
  }

  const statRoles = unique(statIds.flatMap((id) => getStatById(id)?.playerRole ?? []));
  if (sortedMatches.length > 1) {
    if (statRoles.length > 1) {
      return ambiguous("It mixes players with different kinds of stat.");
    }
    // A second name that cannot have the stat is a mention, not a player to compare.
    const fits = (m: PlayerMatch) =>
      candidatePositions(m).some((position) => (ROLES_BY_POSITION[position] ?? []).some((r) => statRoles.includes(r)));
    if (!sortedMatches.every(fits)) {
      return ambiguous("One of the names is not a player who could have that stat.");
    }
  }

  const asked = unique(found.flatMap((f) => (f.piece.kind === "granularity" ? [f.piece.value] : [])));
  if (asked.length > 1) {
    return ambiguous("It asks for more than one of total, per game and per play.");
  }
  const rate = statIds.filter((id) => getStatById(id)?.rate_only);
  const requested = asked[0];
  if (rate.length > 0 && requested !== undefined && requested !== "per_play") {
    return ambiguous("A rate stat has no total or per-game form.");
  }
  if (rate.length > 0 && rate.length < statIds.length && requested !== "per_play") {
    // Rates are per play, counts are totals; one setting would turn the counts into per-play values.
    return ambiguous("It mixes counting stats with rates, which need different settings.");
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
    return ambiguous("It sets two cases side by side (like home and away), which one query can't split.");
  }

  const filterAt: { at: number; id: string }[] = [
    ...found.flatMap((f) => (f.piece.kind === "chips" ? f.piece.ids.map((id) => ({ at: f.at, id })) : [])),
    ...years.map((y) => ({ at: y.at, id: `season-${y.year}` })),
  ];

  const intent: QueryIntent = {
    stat_ids: statIds,
    filter_ids: unique(filterAt.sort((a, b) => a.at - b.at).map((f) => f.id)),
    granularity: rate.length > 0 ? "per_play" : (requested ?? "total"),
  };
  if (!isLeaderboard) {
    return { status: "resolved", intent };
  }
  const metric = statIds[0]!;
  const direction = rankDirection(tokens, metric);
  if (typeof direction !== "string") {
    return ambiguous(direction.reason);
  }
  const minPlays = intent.granularity === "total" ? 0 : LEADERBOARD_MIN_PLAYS;
  return {
    status: "resolved",
    intent,
    leaderboard: { order: { metric, direction }, limit, minPlays },
  };
}

/** Highest first unless the question asks otherwise; asking both ways, or "best" of a neutral stat, is unclear. */
function rankDirection(tokens: readonly string[], metric: string): "asc" | "desc" | { reason: string } {
  const better = getStatById(metric)?.better;
  const asked = new Set<"asc" | "desc">();
  for (const token of tokens) {
    const cue = RANK_DIRECTION.get(token);
    if (cue === "desc" || cue === "asc") {
      asked.add(cue);
    } else if (cue) {
      if (!better) {
        return { reason: `"${token}" has no clear meaning for ${getStatById(metric)?.label ?? metric}; ask for the highest or lowest.` };
      }
      asked.add((cue === "best") === (better === "higher") ? "desc" : "asc");
    }
  }
  if (asked.size > 1) {
    return { reason: "It asks for both the highest and the lowest." };
  }
  return [...asked][0] ?? "desc";
}
