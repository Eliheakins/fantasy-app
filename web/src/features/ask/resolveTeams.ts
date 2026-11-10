import { TEAMS } from "@/stat/config/teams";

import { type PlayerMatch, tokenize } from "./resolvePlayers";

/** A team named in the question and the tokens its name covers. */
export interface TeamMatch {
  id: string;
  start: number;
  length: number;
}

// Full names first, so "Kansas City Chiefs" is one match rather than a stray "kansas city".
// Abbreviations are left out: "NO", "LA" and "NE" are also ordinary words.
const PHRASES = TEAMS.flatMap((team) => [
  { id: team.id, words: tokenize(team.name) },
  { id: team.id, words: tokenize(team.nickname) },
]).sort((a, b) => b.words.length - a.words.length);

/** The teams in already-tokenized text, in reading order, without overlaps. */
export function findTeams(tokens: readonly string[]): TeamMatch[] {
  const used = tokens.map(() => false);
  const found: TeamMatch[] = [];
  for (const { id, words } of PHRASES) {
    for (let i = 0; i + words.length <= tokens.length; i++) {
      if (words.every((word, k) => !used[i + k] && tokens[i + k] === word)) {
        words.forEach((_, k) => {
          used[i + k] = true;
        });
        found.push({ id, start: i, length: words.length });
      }
    }
  }
  return found.sort((a, b) => a.start - b.start);
}

export const resolveTeams = (question: string): TeamMatch[] => findTeams(tokenize(question));

/**
 * Player matches that are not just a team's name: "Bills" is the team even though a lineman is named
 * Keaton Bills, while "Keaton Bills" in full is still the player.
 */
export function dropTeamNames<M extends Pick<PlayerMatch, "phrase" | "start">>(matches: readonly M[], teams: readonly TeamMatch[]): M[] {
  return matches.filter((m) => {
    const end = m.start + tokenize(m.phrase).length;
    return !teams.some((t) => t.start <= m.start && end <= t.start + t.length);
  });
}
