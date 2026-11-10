import type { Side } from "@/stat/types/queryBuilder";

import { LEADERBOARD_CUES } from "../ranking";
import { readOpponents } from "../opponents";
import { type PlayerMatch, tokenize } from "../resolvePlayers";
import { findTeams, type TeamMatch } from "../resolveTeams";
import { ambiguous, proceed, type RuleContext, type Stage, stop } from "./types";
import {
  DEFENSE_WORDS,
  OFFENSE_WORDS,
  TEAM_WORDS,
  UNIT_NOUNS,
  unique,
  wordsOf,
  YEAR_RANGE,
} from "./vocab";

/** Who the question is about: the players, teams and opponents it names, and whether it ranks. */
export interface Entities {
  tokens: string[];
  matches: readonly PlayerMatch[];
  sortedMatches: PlayerMatch[];
  teams: TeamMatch[];
  opponents: ReturnType<typeof readOpponents>;
  opponentWords: ReadonlySet<number>;
  asksTeams: boolean;
  isLeaderboard: boolean;
}

/**
 * For a question that names no player: the teams it is about and the side of the ball, or null when it
 * is not about teams. "which team", "defense" and a team name make it a team question.
 */
export function teamsAsked(question: string): { ids: string[]; side: Side } | null {
  const tokens = wordsOf(question);
  const opponentWords = new Set(readOpponents(question, false).used);
  const named = findTeams(tokens).filter((t) => !opponentWords.has(t.start));
  if (named.length === 0 && !tokens.some((t) => TEAM_WORDS.has(t) || UNIT_NOUNS.has(t))) {
    return null;
  }
  const defense = tokens.some((t, at) => DEFENSE_WORDS.has(t) && !opponentWords.has(at));
  return { ids: unique(named.map((t) => t.id)), side: defense ? "defense" : "offense" };
}

/** True when the question uses a word that asks for a ranking ("most", "top", "leads"). */
export const asksRanking = (question: string): boolean => wordsOf(question).some((t) => LEADERBOARD_CUES.has(t));

/** Finds the players, teams and opponents, and refuses what cannot be a question about one subject. */
export function readEntities(question: string, context: RuleContext): Stage<Entities> {
  const { matches, seasons } = context;
  const tokens = wordsOf(question);
  // A team name inside a player's name ("Keaton Bills") is part of the player, not a team.
  const inPlayer = (at: number) => matches.some((m) => at >= m.start && at < m.start + tokenize(m.phrase).length);
  // "against the Cowboys" names an opponent (a chip), not the team the question is about.
  const opponents = readOpponents(question, matches.length > 0);
  const opponentWords = new Set(opponents.used);
  const teams = findTeams(tokens).filter((t) => !inPlayer(t.start) && !opponentWords.has(t.start));
  const asksTeams =
    teams.length > 0 || (matches.length === 0 && tokens.some((t) => TEAM_WORDS.has(t) || UNIT_NOUNS.has(t)));
  if (teams.length > 0 && matches.length > 0) {
    // A player and a team that is not an opponent: which one the question is about is unclear. The
    // team words are listed as unread, so a model answer that ignores them says so.
    const inTeam = (at: number) => teams.some((t) => at >= t.start && at < t.start + t.length);
    const unread = tokens.filter((t, at) => inTeam(at) || DEFENSE_WORDS.has(t) || OFFENSE_WORDS.has(t));
    return stop(ambiguous("It names a player and a team; ask about one of them.", unique(unread)));
  }
  const isLeaderboard = matches.length === 0 && teams.length === 0 && tokens.some((t) => LEADERBOARD_CUES.has(t));
  if (matches.length === 0 && teams.length === 0 && !isLeaderboard) {
    return stop({ status: "unknown", reason: "No player was named." });
  }
  if (seasons.length === 0) {
    return stop({ status: "unknown", reason: "The data has no seasons." });
  }
  if (YEAR_RANGE.test(question)) {
    return stop(
      ambiguous("It names a range of seasons, which is read as a list of years only when each is written out."),
    );
  }
  const sortedMatches = [...matches].sort((a, b) => a.start - b.start);
  return proceed({ tokens, matches, sortedMatches, teams, opponents, opponentWords, asksTeams, isLeaderboard });
}
