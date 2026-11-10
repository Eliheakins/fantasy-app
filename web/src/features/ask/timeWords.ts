/**
 * Relative time, read in code on every path: "this season", "last year", "week 3", "weeks 3 to 6",
 * "since week 5", "last week", "last 3 games", "career". The model is weak at numbers and dates, so
 * these words are cut from the text it sees and put back here.
 */
import { MAX_WEEK } from "@/stat/config/queryBuilderOptions";
import { MAX_LAST_GAMES } from "@/stat/lib/queryUrl";

import { tokenize } from "./resolvePlayers";

/** The seasons the data has and the latest week each reaches (from the manifest). */
export interface TimeScope {
  seasons: readonly number[];
  maxWeeks?: Readonly<Record<number, number>>;
}

export interface TimeRead {
  /** season-* and wk-* chips the words name. */
  filters: string[];
  /** "last 3 games": each player's latest N games. */
  lastGames: number | null;
  /** "career", "all time": every season on purpose. */
  career: boolean;
  /** Indices (into the question's tokens) of the words read here. */
  used: number[];
  /** The question's words without the ones read here, for the model; the question itself when none were. */
  rest: string;
  /** What a relative word was read as, in plain words ("last week: week 8, the latest in the data"). */
  notes: string[];
  /** Words that name a time the data cannot give (a week past the latest one). */
  problem: string | null;
}

const NUMBER_WORDS: Readonly<Record<string, number>> = {
  one: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
  six: 6,
  seven: 7,
  eight: 8,
  nine: 9,
  ten: 10,
};
const SEASON_WORDS = new Set(["season", "year", "szn", "seasons", "years"]);
const GAME_WORDS = new Set(["games", "weeks", "game", "starts"]);
const RANGE_JOINS = new Set(["to", "through", "thru", "and", "until"]);
const YEAR = /^(19|20)\d\d$/;

const numberAt = (tokens: readonly string[], at: number): number | null => {
  const token = tokens[at] ?? "";
  if (/^\d+$/.test(token)) {
    return Number(token);
  }
  return NUMBER_WORDS[token] ?? null;
};

/** What the readers have found so far in one question. Built up in place; local to one `readTime` call. */
interface TimeState {
  tokens: readonly string[];
  /** The latest season in the data, or null when it has none. */
  current: number | null;
  used: Set<number>;
  seasons: Set<number>;
  weeks: Set<number>;
  notes: string[];
  lastGames: number | null;
  career: boolean;
  problem: string | null;
  sinceWeek: { from: number; at: number[] } | null;
  /** The last week to read for a season: the data's own, else week 22 (null for a current season with none). */
  lastWeekOf: (season: number | null) => number | null;
}

/** The word being read and the two after it. */
interface Cursor {
  i: number;
  t: string;
  next: string;
  after: string;
}

/** `pattern` says the words start this reading (the first reader whose pattern fits is the only one tried). */
interface WordReader {
  pattern: (c: Cursor, s: TimeState) => boolean;
  apply: (c: Cursor, s: TimeState) => void;
}

const take = (s: TimeState, ...at: number[]): void => at.forEach((i) => s.used.add(i));
const ONWARD_WORDS = ["on", "onward", "onwards"];

/** The readers for words that start a time phrase, in the order they are tried. */
const WORD_READERS: readonly WordReader[] = [
  {
    // this season
    pattern: (c, s) => (c.t === "this" || c.t === "current") && SEASON_WORDS.has(c.next) && s.current !== null,
    apply: (c, s) => {
      s.seasons.add(s.current!);
      take(s, c.i, c.i + 1);
    },
  },
  {
    // last year
    pattern: (c, s) =>
      (c.t === "last" || c.t === "previous" || c.t === "prior") && SEASON_WORDS.has(c.next) && s.current !== null,
    apply: (c, s) => {
      s.seasons.add(s.current! - 1);
      take(s, c.i, c.i + 1);
    },
  },
  {
    // two seasons ago
    pattern: (c, s) =>
      numberAt(s.tokens, c.i) === 2 && SEASON_WORDS.has(c.next) && c.after === "ago" && s.current !== null,
    apply: (c, s) => {
      s.seasons.add(s.current! - 2);
      take(s, c.i, c.i + 1, c.i + 2);
    },
  },
  {
    // career, lifetime, all time
    pattern: (c) => c.t === "career" || c.t === "lifetime" || (c.t === "all" && c.next === "time"),
    apply: (c, s) => {
      s.career = true;
      take(s, ...(c.t === "all" ? [c.i, c.i + 1] : [c.i]));
    },
  },
  {
    // this week, last week: the latest week with data, since this week's games may not be played yet
    pattern: (c) => (c.t === "this" || c.t === "last" || c.t === "past") && c.next === "week",
    apply: (c, s) => {
      const latest = s.lastWeekOf(s.current);
      if (latest === null || s.current === null) {
        s.problem = "The latest week in the data is not known.";
      } else {
        s.weeks.add(latest);
        s.seasons.add(s.current);
        s.notes.push(`"${c.t} week" is read as week ${latest} of ${s.current}, the latest week in the data.`);
      }
      take(s, c.i, c.i + 1);
    },
  },
  {
    // last game, last 3 games
    pattern: (c) =>
      (c.t === "last" || c.t === "past" || c.t === "previous") && (GAME_WORDS.has(c.next) || GAME_WORDS.has(c.after)),
    apply: (c, s) => {
      const n = GAME_WORDS.has(c.next) ? 1 : numberAt(s.tokens, c.i + 1);
      if (n !== null && n >= 1 && n <= MAX_LAST_GAMES) {
        s.lastGames = n;
        take(s, ...(GAME_WORDS.has(c.next) ? [c.i, c.i + 1] : [c.i, c.i + 1, c.i + 2]));
      }
    },
  },
  {
    // since week 5, after week 5, from week 5 onward
    pattern: (c) => (c.t === "since" || c.t === "after" || c.t === "from") && (c.next === "week" || c.next === "wk"),
    apply: (c, s) => {
      const n = numberAt(s.tokens, c.i + 2);
      if (n === null) {
        return;
      }
      const joined = s.tokens[c.i + 3] ?? "";
      const at = [c.i, c.i + 1, c.i + 2];
      // "from week 3 to week 6" is a range, read by the week reader.
      if (c.t === "from" && RANGE_JOINS.has(joined)) {
        at.forEach((i) => s.used.delete(i));
        s.sinceWeek = null;
        return;
      }
      s.sinceWeek = { from: c.t === "after" ? n + 1 : n, at };
      take(s, ...at);
      if (ONWARD_WORDS.includes(joined)) {
        take(s, c.i + 3);
      }
    },
  },
];

/** week 3 / weeks 3 to 6 / weeks 3 6 ("weeks 3-6") / week 3 or later */
function readWeekSpan(c: Cursor, s: TimeState): void {
  const { tokens } = s;
  if (c.t !== "week" && c.t !== "weeks" && c.t !== "wk" && c.t !== "wks") {
    return;
  }
  const from = numberAt(tokens, c.i + 1);
  if (from === null) {
    return;
  }
  const at = [c.i, c.i + 1];
  const k = c.i + 2;
  let to = from;
  if (RANGE_JOINS.has(tokens[k] ?? "")) {
    const weekWord = tokens[k + 1] === "week" || tokens[k + 1] === "wk";
    const second = numberAt(tokens, weekWord ? k + 2 : k + 1);
    if (second !== null && second >= from) {
      to = second;
      at.push(...(weekWord ? [k, k + 1, k + 2] : [k, k + 1]));
    }
  } else if (c.t.endsWith("s") && (numberAt(tokens, k) ?? -1) >= from) {
    to = numberAt(tokens, k)!;
    at.push(k);
  } else if (
    ONWARD_WORDS.includes(tokens[k] ?? "") ||
    (tokens[k] === "or" && ["later", "after"].includes(tokens[k + 1] ?? ""))
  ) {
    s.sinceWeek = { from, at: tokens[k] === "or" ? [...at, k, k + 1] : [...at, k] };
    take(s, ...s.sinceWeek.at);
    return;
  }
  // "from week 3 to week 6", "between weeks 3 and 6"
  if (tokens[c.i - 1] === "from" || tokens[c.i - 1] === "between") {
    at.push(c.i - 1);
  }
  take(s, ...at);
  for (let w = from; w <= to; w++) {
    s.weeks.add(w);
  }
}

/** `skip`: token indices another reader already took ("week 13 or later" is a chip phrase). */
export function readTime(question: string, scope: TimeScope, skip: ReadonlySet<number> = new Set()): TimeRead {
  const tokens = tokenize(question.replace(/%/g, " percent "));
  const current = scope.seasons.length > 0 ? Math.max(...scope.seasons) : null;
  const s: TimeState = {
    tokens,
    current,
    used: new Set(),
    seasons: new Set(),
    weeks: new Set(),
    notes: [],
    lastGames: null,
    career: false,
    problem: null,
    sinceWeek: null,
    lastWeekOf: (season) =>
      (season !== null ? scope.maxWeeks?.[season] : undefined) ?? (season === current ? null : MAX_WEEK),
  };
  const years = tokens.filter((t) => YEAR.test(t)).map(Number);

  for (let i = 0; i < tokens.length; i++) {
    const cursor: Cursor = { i, t: tokens[i]!, next: tokens[i + 1] ?? "", after: tokens[i + 2] ?? "" };
    if (s.used.has(i) || skip.has(i)) {
      continue;
    }
    WORD_READERS.find((r) => r.pattern(cursor, s))?.apply(cursor, s);
    if (!s.used.has(i)) {
      readWeekSpan(cursor, s);
    }
  }
  // The season a bare week belongs to: the one year or relative season named, else the current season.
  const named = [...new Set([...years, ...s.seasons])];
  const weekSeason = named.length === 1 ? named[0]! : current;
  if (s.sinceWeek) {
    const latest = s.lastWeekOf(weekSeason);
    if (latest === null) {
      s.problem = "The latest week in the data is not known.";
    } else {
      for (let w = s.sinceWeek.from; w <= latest; w++) {
        s.weeks.add(w);
      }
    }
  }
  const latest = s.lastWeekOf(weekSeason);
  if ([...s.weeks].some((w) => w < 1 || w > MAX_WEEK || (latest !== null && w > latest))) {
    s.problem = `The data for ${weekSeason} reaches week ${latest ?? MAX_WEEK}.`;
  }
  const filters = [
    ...[...s.seasons].sort().map((x) => `season-${x}`),
    ...[...s.weeks].sort((a, b) => a - b).map((w) => `wk-${w}`),
  ];
  return {
    filters,
    lastGames: s.lastGames,
    career: s.career,
    used: [...s.used].sort((a, b) => a - b),
    rest: s.used.size === 0 ? question : tokens.filter((_, i) => !s.used.has(i)).join(" "),
    notes: s.notes,
    problem: s.problem,
  };
}

/** The intent's filters with the time words read in code put in place of the model's own reading of them. */
export function withTime(filters: readonly string[], time: TimeRead): string[] {
  const named = (prefix: string) => time.filters.some((f) => f.startsWith(prefix));
  const kept = filters.filter(
    (f) =>
      !(named("season-") && f.startsWith("season-")) &&
      !(named("wk-") && (f.startsWith("wk-") || f.startsWith("week-"))),
  );
  return [...new Set([...kept, ...time.filters])];
}
