import type { Side } from "@/stat/types/queryBuilder";

import { readLimit, readMinimum, readWho } from "../ranking";
import { readRoster } from "../rosterWords";
import { NAME_SUFFIXES, tokenize } from "../resolvePlayers";
import type { Entities } from "./entities";
import { findSplit, type SplitRead } from "./split";
import { ambiguous, proceed, type Stage, stop, type WordMask } from "./types";
import { asksDefense, COMPARE_WORDS, DEFENSE_WORDS, NAMED_COMPARE_WORDS, OFFENSE_WORDS, TEAM_FILLER, TEAM_WORDS } from "./vocab";

/** The question's frame: which words are names or framing, the side of the ball, and the split asked for. */
export interface Structure {
  used: WordMask;
  side: Side;
  split: SplitRead;
}

/** Marks the words of names, teams and opponents as read. */
function claimNames(e: Entities): WordMask {
  const { tokens, sortedMatches, teams, opponents } = e;
  const used = tokens.map(() => false);
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
  for (const at of opponents.used) {
    used[at] = true;
  }
  return used;
}

/** "Kelce vs Kittle", "Compare Kelce and Kittle" and "Henry or Barkley" set names side by side; marks those words read. */
function claimComparisons(e: Entities, used: WordMask, isName: readonly boolean[]): void {
  const { tokens, matches } = e;
  // Anywhere else these words are unread.
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
}

/** Reads names, the side of the ball, comparisons, a ranking's limit, minimum and position words, and the split. */
export function claimStructure(e: Entities): Stage<Structure> {
  const { tokens, asksTeams, opponentWords, isLeaderboard } = e;
  const used = claimNames(e);
  let side: Side = "offense";
  if (asksTeams) {
    const defense = asksDefense(tokens, opponentWords);
    if (defense && tokens.some((t) => OFFENSE_WORDS.has(t))) {
      return stop(ambiguous("It asks for a team's offense and defense at once."));
    }
    side = defense ? "defense" : "offense";
    tokens.forEach((token, at) => {
      used[at] ||= TEAM_WORDS.has(token) || DEFENSE_WORDS.has(token) || OFFENSE_WORDS.has(token) || TEAM_FILLER.has(token);
    });
  }
  claimComparisons(e, used, [...used]);

  if (isLeaderboard) {
    // "top 5", "fewest 5": the number after a ranking word is the limit, not a stat or a season.
    const limit = readLimit(tokens);
    if (limit && "reason" in limit) {
      return stop(ambiguous(limit.reason));
    }
    // "min 100 carries", "tight ends", "rookies": read here; leaderboardFor checks they fit the stat.
    const roster = readRoster(tokens);
    if (roster.reason) {
      return stop(ambiguous(roster.reason));
    }
    for (const at of [...(limit ? [limit.at] : []), ...(readMinimum(tokens)?.at ?? []), ...readWho(tokens).at, ...roster.at]) {
      used[at] = true;
    }
  }

  // The split is applied by Ask whichever path answers; here its words only count as read.
  const split = findSplit(tokens);
  if (split.split === "both") {
    return stop(ambiguous("It asks to split by season and by week at once."));
  }
  for (const at of split.at) {
    used[at] = true;
  }
  return proceed({ used, side, split });
}
