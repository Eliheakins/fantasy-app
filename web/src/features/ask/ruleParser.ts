/**
 * A deterministic first pass at turning a question into stats, filters and a granularity. It only
 * answers when it understands every word; anything else is handed back so the model can try. A wrong
 * answer given with confidence is the failure to avoid, so an unrecognised word means "not sure",
 * never "ignore it".
 */
import { CHIP_COMBO_PHRASES, CHIP_PHRASES, type FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import { getStatById, type PlayerRole, STAT_DEFINITIONS } from "@/stat/config/statDictionary";
import { MAX_SELECTED_STATS } from "@/stat/lib/queryUrl";
import type { QueryIntent } from "@/stat/lib/schemas/nlqIntent";
import type { GranularityMode, Side, Split } from "@/stat/types/queryBuilder";

import { NAME_SUFFIXES, type PlayerMatch, tokenize } from "./resolvePlayers";
import {
  type Leaderboard,
  LEADERBOARD_CUES,
  leaderboardFor,
  readLimit,
  readMinimum,
  readSingleGame,
} from "./ranking";
import { findTeams } from "./resolveTeams";
import { readTime } from "./timeWords";

export interface RuleContext {
  /** Players already found in the question (their words are not part of the stat wording). */
  matches: readonly PlayerMatch[];
  /** Seasons the data has. */
  seasons: readonly number[];
  chipGroups: readonly FilterChipGroup[];
  /** The latest week each season reaches, for "last week" and "since week 5". */
  maxWeeks?: Readonly<Record<number, number>>;
}

export type { Leaderboard };

export type RuleResult =
  /** `team`: the question is about teams (none named means a ranking of all 32). */
  | { status: "resolved"; intent: QueryIntent; leaderboard?: Leaderboard; team?: { ids: string[]; side: Side } }
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
  "a",
  "an",
  "the",
  "in",
  "on",
  "at",
  "of",
  "for",
  "and",
  "what",
  "whats",
  "was",
  "were",
  "is",
  "are",
  "how",
  "many",
  "much",
  "did",
  "do",
  "does",
  "had",
  "has",
  "have",
  "his",
  "their",
  "during",
  "me",
  "show",
  "tell",
  "give",
  "get",
  "got",
  "s",
]);

/**
 * Words that only mean "compare" between two player names ("Kelce vs Kittle"). Next to a stat, season
 * or situation they set two cases side by side, which one query cannot split, so they stay unread.
 */
const COMPARE_WORDS = new Set(["vs", "versus", "compare"]);

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

/** The one role a position is mainly known for, used to read a bare "yards" and to pick a stat family's member. */
export const MAIN_ROLE: Readonly<Record<string, PlayerRole>> = {
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

/** Words a leaderboard question uses around its stat; read as filler only when no player is named. */
const LEADERBOARD_WORDS = new Set([
  ...LEADERBOARD_CUES,
  "who",
  "league",
  "nfl",
  "by",
  "with",
  "among",
  "qualified",
  "players",
  "in",
]);
/** "Who had more rushing yards, Henry or Barkley": between or before two names these only set them side by side. */
const NAMED_COMPARE_WORDS = new Set(["who", "had", "has", "more", "better", "or"]);
/** Words that make a question about teams, and that pick the side of the ball. */
const TEAM_WORDS = new Set(["team", "teams"]);
const DEFENSE_WORDS = new Set(["allowed", "allow", "allows", "against", "defense", "defenses", "defensive"]);
const OFFENSE_WORDS = new Set(["offense", "offenses", "offensive"]);
/** "allowed by the Chiefs", "which team": read as filler only in a team question. */
const TEAM_FILLER = new Set(["by", "which"]);

/** "by season", "each game", "every year": a word that asks for a split, then the unit. */
const SPLIT_LEADS = new Set(["by", "each", "every", "per"]);
/** "per game" is a granularity, so "per" only splits by season. */
const PER_SPLITS = new Set(["season", "seasons", "year", "years"]);
const SPLIT_UNITS = new Map<string, Split>([
  ["season", "season"],
  ["seasons", "season"],
  ["year", "season"],
  ["years", "season"],
  ["week", "week"],
  ["weeks", "week"],
  ["game", "week"],
  ["games", "week"],
]);

/** Which split the words ask for, and where they are; "season by season" counts like "by season". */
function findSplit(tokens: readonly string[]): { split: Split | "both" | null; at: number[] } {
  const asked = new Set<Split>();
  const at: number[] = [];
  tokens.forEach((token, i) => {
    const next = tokens[i + 1] ?? "";
    const unit = SPLIT_UNITS.get(next);
    // "by week 5" names a week, not a split.
    const namesOne = /^\d+$/.test(tokens[i + 2] ?? "");
    if (SPLIT_LEADS.has(token) && unit && !namesOne && (token !== "per" || PER_SPLITS.has(next))) {
      asked.add(unit);
      at.push(i, i + 1);
      if (tokens[i - 1] !== undefined && SPLIT_UNITS.get(tokens[i - 1]!) === unit) {
        at.push(i - 1);
      }
    }
  });
  // "most passing yards in a single game" ranks single games: a split by week.
  const single = readSingleGame(tokens);
  if (single) {
    asked.add("week");
    at.push(...single);
  }
  return { split: asked.size > 1 ? "both" : ([...asked][0] ?? null), at };
}

/** The split a question asks for, whichever path reads the rest of it; "both" means it asks for two. */
export const splitAsked = (question: string): Split | "both" | null => findSplit(wordsOf(question)).split;

/**
 * For a question that names no player: the teams it is about and the side of the ball, or null when it
 * is not about teams. "which team", "defense" and a team name make it a team question.
 */
export function teamsAsked(question: string): { ids: string[]; side: Side } | null {
  const tokens = wordsOf(question);
  const named = findTeams(tokens);
  // "allowed" alone does not make a team question ("most yards allowed" could be anything); "defense" does.
  const unitNouns = new Set(["defense", "defenses", "offense", "offenses"]);
  if (named.length === 0 && !tokens.some((t) => TEAM_WORDS.has(t) || unitNouns.has(t))) {
    return null;
  }
  return { ids: unique(named.map((t) => t.id)), side: tokens.some((t) => DEFENSE_WORDS.has(t)) ? "defense" : "offense" };
}

/** True when the question uses a word that asks for a ranking ("most", "top", "leads"). */
export const asksRanking = (question: string): boolean => wordsOf(question).some((t) => LEADERBOARD_CUES.has(t));

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
  // A team name inside a player's name ("Keaton Bills") is part of the player, not a team.
  const inPlayer = (at: number) => matches.some((m) => at >= m.start && at < m.start + tokenize(m.phrase).length);
  const teams = findTeams(tokensForCue).filter((t) => !inPlayer(t.start));
  const asksTeams = teams.length > 0 || (matches.length === 0 && tokensForCue.some((t) => TEAM_WORDS.has(t)));
  if (teams.length > 0 && matches.length > 0) {
    // "Mahomes against the Chiefs" is an opponent filter, which the data cannot apply. The team words
    // are listed as unread, so a model answer that ignores them says so.
    const inTeam = (at: number) => teams.some((t) => at >= t.start && at < t.start + t.length);
    const unread = tokensForCue.filter((t, at) => inTeam(at) || DEFENSE_WORDS.has(t) || OFFENSE_WORDS.has(t));
    return ambiguous("It names a player and a team; ask about one of them.", unique(unread));
  }
  const isLeaderboard = matches.length === 0 && teams.length === 0 && tokensForCue.some((t) => LEADERBOARD_CUES.has(t));
  if (matches.length === 0 && teams.length === 0 && !isLeaderboard) {
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
  for (const team of teams) {
    for (let i = team.start; i < team.start + team.length; i++) {
      used[i] = true;
    }
  }
  let side: Side = "offense";
  if (asksTeams) {
    const defense = tokens.some((t) => DEFENSE_WORDS.has(t));
    if (defense && tokens.some((t) => OFFENSE_WORDS.has(t))) {
      return ambiguous("It asks for a team's offense and defense at once.");
    }
    side = defense ? "defense" : "offense";
    tokens.forEach((token, at) => {
      used[at] ||=
        TEAM_WORDS.has(token) || DEFENSE_WORDS.has(token) || OFFENSE_WORDS.has(token) || TEAM_FILLER.has(token);
    });
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
  // "Who had more rushing yards, Henry or Barkley": an "or" between two names sets them side by side.
  if (matches.length > 1 && tokens.some((t, at) => t === "or" && isName[at - 1] && isName[at + 1])) {
    tokens.forEach((token, at) => {
      used[at] ||= NAMED_COMPARE_WORDS.has(token) && (token !== "or" || Boolean(isName[at - 1] && isName[at + 1]));
    });
  }

  if (isLeaderboard) {
    // "top 5", "fewest 5": the number after a ranking word is the limit, not a stat or a season.
    const limit = readLimit(tokens);
    if (limit && "reason" in limit) {
      return ambiguous(limit.reason);
    }
    // "min 100 carries": the floor's words are read here; leaderboardFor checks its unit.
    for (const at of [...(limit ? [limit.at] : []), ...(readMinimum(tokens)?.at ?? [])]) {
      used[at] = true;
    }
  }

  // The split is applied by Ask whichever path answers; here its words only count as read.
  const split = findSplit(tokens);
  if (split.split === "both") {
    return ambiguous("It asks to split by season and by week at once.");
  }
  for (const at of split.at) {
    used[at] = true;
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

  // "this season", "week 3", "since week 5", "last 3 games": read after the chip phrases ("week 13 or later").
  const time = readTime(question, { seasons, maxWeeks: context.maxWeeks }, new Set(used.flatMap((u, at) => (u ? [at] : []))));
  if (time.problem) {
    return { status: "unsupported", reason: time.problem };
  }
  for (const at of time.used) {
    used[at] = true;
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

  const statAt: { at: number; id: string }[] = found.flatMap((f) =>
    f.piece.kind === "stat" ? [{ at: f.at, id: f.piece.id }] : [],
  );
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

  // A league stat (fantasy points) belongs to no position, so it settles no role.
  const statRoles = unique(
    statIds.flatMap((id) => {
      const stat = getStatById(id);
      return stat && stat.source !== "league" ? [stat.playerRole] : [];
    }),
  );
  if (sortedMatches.length > 1) {
    if (statRoles.length > 1) {
      return ambiguous("It mixes players with different kinds of stat.");
    }
    // A second name that cannot have the stat is a mention, not a player to compare.
    const fits = (m: PlayerMatch) =>
      statRoles.length === 0 ||
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
    ...time.filters.map((id) => ({ at: time.used[0] ?? 0, id })),
  ];

  const intent: QueryIntent = {
    stat_ids: statIds,
    filter_ids: unique(filterAt.sort((a, b) => a.at - b.at).map((f) => f.id)),
    granularity: rate.length > 0 ? "per_play" : (requested ?? "total"),
  };
  if (asksTeams && statIds.some((id) => getStatById(id)?.category.startsWith("ngs_"))) {
    return {
      status: "unsupported",
      reason: "Next Gen Stats are per-player weekly values, so a team has no total for them.",
    };
  }
  const team = asksTeams ? { team: { ids: unique(teams.map((t) => t.id)), side } } : {};
  if (!isLeaderboard) {
    return { status: "resolved", intent, ...team };
  }
  const leaderboard = leaderboardFor(tokens, statIds[0]!, intent.granularity, {
    teams: asksTeams,
    defense: side === "defense",
    weekly: split.split === "week",
  });
  if ("reason" in leaderboard) {
    return ambiguous(leaderboard.reason);
  }
  return { status: "resolved", intent, leaderboard, ...team };
}
