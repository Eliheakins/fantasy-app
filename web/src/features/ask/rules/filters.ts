import { readTime, type TimeRead } from "../timeWords";
import type { Entities } from "./entities";
import { type Found, findPhrases, namesPartOfSomething } from "./phrases";
import { ambiguous, proceed, type RuleContext, type Stage, stop, type WordMask } from "./types";
import { SEASON_CONTEXT, YEAR } from "./vocab";

export interface YearMention {
  at: number;
  year: number;
}

/** The stat, chip and granularity phrases, the time words and the season years the question names. */
export interface FilterReads {
  found: Found[];
  time: TimeRead;
  years: YearMention[];
}

/** Years the data has become season filters; a year outside it is refused, with the range the data covers. */
function readYears(tokens: readonly string[], used: WordMask, seasons: readonly number[]): Stage<YearMention[]> {
  const years: YearMention[] = [];
  let missingYear: YearMention | undefined;
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
    return stop({
      status: "unsupported",
      reason: `The data covers ${first}–${last}; ${missingYear.year} isn't in it.`,
    });
  }
  // "the 2023 season" and "season 2023" are fine; a season with no year ("in a season") is not a filter.
  tokens.forEach((token, at) => {
    if (!used[at] && (token === "season" || token === "seasons")) {
      used[at] = years.some((y) => y.at === at - 1 || y.at === at + 1);
    }
  });
  return proceed(years);
}

/** Reads the phrases and the time and season words, marking each as read. */
export function readFilters(
  question: string,
  context: RuleContext,
  e: Entities,
  used: WordMask,
): Stage<FilterReads> {
  const { tokens } = e;
  const { seasons, chipGroups } = context;
  const chipIds = new Set(chipGroups.flatMap((g) => g.options.map((o) => o.id)));
  const found = findPhrases(tokens, used, chipIds);
  if (namesPartOfSomething(found, tokens)) {
    return stop(ambiguous("It names part of a game followed by 'of', which is not a part of a game."));
  }

  // "this season", "week 3", "since week 5", "last 3 games": read after the chip phrases ("week 13 or later").
  const time = readTime(
    question,
    { seasons, maxWeeks: context.maxWeeks },
    new Set(used.flatMap((u, at) => (u ? [at] : []))),
  );
  if (time.problem) {
    return stop({ status: "unsupported", reason: time.problem });
  }
  for (const at of time.used) {
    used[at] = true;
  }

  const years = readYears(tokens, used, seasons);
  return years.ok ? proceed({ found, time, years: years.value }) : years;
}
