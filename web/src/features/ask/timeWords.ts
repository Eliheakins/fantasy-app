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

/** `skip`: token indices another reader already took ("week 13 or later" is a chip phrase). */
export function readTime(question: string, scope: TimeScope, skip: ReadonlySet<number> = new Set()): TimeRead {
  const tokens = tokenize(question.replace(/%/g, " percent "));
  const used = new Set<number>();
  const take = (...at: number[]) => at.forEach((i) => used.add(i));
  const current = scope.seasons.length > 0 ? Math.max(...scope.seasons) : null;
  const seasons = new Set<number>();
  const weeks = new Set<number>();
  const notes: string[] = [];
  let lastGames: number | null = null;
  let career = false;
  let problem: string | null = null;
  let sinceWeek: { from: number; at: number[] } | null = null;
  const years = tokens.filter((t) => YEAR.test(t)).map(Number);
  const lastWeekOf = (season: number | null) =>
    (season !== null ? scope.maxWeeks?.[season] : undefined) ?? (season === current ? null : MAX_WEEK);

  for (let i = 0; i < tokens.length; i++) {
    const [t, next, after] = [tokens[i]!, tokens[i + 1] ?? "", tokens[i + 2] ?? ""];
    if (used.has(i) || skip.has(i)) {
      continue;
    }
    // this season / last year / two seasons ago
    if ((t === "this" || t === "current") && SEASON_WORDS.has(next) && current !== null) {
      seasons.add(current);
      take(i, i + 1);
    } else if ((t === "last" || t === "previous" || t === "prior") && SEASON_WORDS.has(next) && current !== null) {
      seasons.add(current - 1);
      take(i, i + 1);
    } else if (numberAt(tokens, i) === 2 && SEASON_WORDS.has(next) && after === "ago" && current !== null) {
      seasons.add(current - 2);
      take(i, i + 1, i + 2);
    } else if (t === "career" || t === "lifetime" || (t === "all" && next === "time")) {
      career = true;
      take(...(t === "all" ? [i, i + 1] : [i]));
    } else if ((t === "this" || t === "last" || t === "past") && next === "week") {
      // The latest week with data: this week's games may not be played yet.
      const latest = lastWeekOf(current);
      if (latest === null || current === null) {
        problem = "The latest week in the data is not known.";
      } else {
        weeks.add(latest);
        seasons.add(current);
        notes.push(`"${t} week" is read as week ${latest} of ${current}, the latest week in the data.`);
      }
      take(i, i + 1);
    } else if ((t === "last" || t === "past" || t === "previous") && (GAME_WORDS.has(next) || GAME_WORDS.has(after))) {
      const n = GAME_WORDS.has(next) ? 1 : numberAt(tokens, i + 1);
      if (n !== null && n >= 1 && n <= MAX_LAST_GAMES) {
        lastGames = n;
        take(...(GAME_WORDS.has(next) ? [i, i + 1] : [i, i + 1, i + 2]));
      }
    } else if ((t === "since" || t === "after" || t === "from") && (next === "week" || next === "wk")) {
      const n = numberAt(tokens, i + 2);
      if (n !== null) {
        sinceWeek = { from: t === "after" ? n + 1 : n, at: [i, i + 1, i + 2] };
        take(i, i + 1, i + 2);
        // "from week 3 to week 6" is a range, read below.
        if (t === "from" && RANGE_JOINS.has(tokens[i + 3] ?? "")) {
          used.delete(i);
          used.delete(i + 1);
          used.delete(i + 2);
          sinceWeek = null;
        } else if (["on", "onward", "onwards"].includes(tokens[i + 3] ?? "")) {
          take(i + 3);
        }
      }
    }
    if (used.has(i)) {
      continue;
    }
    // week 3 / weeks 3 to 6 / weeks 3 6 ("weeks 3-6") / week 3 or later
    if (t === "week" || t === "weeks" || t === "wk" || t === "wks") {
      const from = numberAt(tokens, i + 1);
      if (from === null) {
        continue;
      }
      const at = [i, i + 1];
      const k = i + 2;
      let to = from;
      if (RANGE_JOINS.has(tokens[k] ?? "")) {
        const weekWord = tokens[k + 1] === "week" || tokens[k + 1] === "wk";
        const second = numberAt(tokens, weekWord ? k + 2 : k + 1);
        if (second !== null && second >= from) {
          to = second;
          at.push(...(weekWord ? [k, k + 1, k + 2] : [k, k + 1]));
        }
      } else if (t.endsWith("s") && (numberAt(tokens, k) ?? -1) >= from) {
        to = numberAt(tokens, k)!;
        at.push(k);
      } else if (
        ["on", "onward", "onwards"].includes(tokens[k] ?? "") ||
        (tokens[k] === "or" && ["later", "after"].includes(tokens[k + 1] ?? ""))
      ) {
        sinceWeek = { from, at: tokens[k] === "or" ? [...at, k, k + 1] : [...at, k] };
        take(...sinceWeek.at);
        continue;
      }
      // "from week 3 to week 6", "between weeks 3 and 6"
      if (tokens[i - 1] === "from" || tokens[i - 1] === "between") {
        at.push(i - 1);
      }
      take(...at);
      for (let w = from; w <= to; w++) {
        weeks.add(w);
      }
    }
  }
  // The season a bare week belongs to: the one year or relative season named, else the current season.
  const named = [...new Set([...years, ...seasons])];
  const weekSeason = named.length === 1 ? named[0]! : current;
  if (sinceWeek) {
    const latest = lastWeekOf(weekSeason);
    if (latest === null) {
      problem = "The latest week in the data is not known.";
    } else {
      for (let w = sinceWeek.from; w <= latest; w++) {
        weeks.add(w);
      }
    }
  }
  const latest = lastWeekOf(weekSeason);
  if ([...weeks].some((w) => w < 1 || w > MAX_WEEK || (latest !== null && w > latest))) {
    problem = `The data for ${weekSeason} reaches week ${latest ?? MAX_WEEK}.`;
  }
  const filters = [
    ...[...seasons].sort().map((s) => `season-${s}`),
    ...[...weeks].sort((a, b) => a - b).map((w) => `wk-${w}`),
  ];
  return {
    filters,
    lastGames,
    career,
    used: [...used].sort((a, b) => a - b),
    rest: used.size === 0 ? question : tokens.filter((_, i) => !used.has(i)).join(" "),
    notes,
    problem,
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
