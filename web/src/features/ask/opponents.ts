/**
 * Opponents, read in code on every path: "against the Cowboys", "vs the Bills", "facing Dallas". The
 * team becomes an `opp-` chip (the defense the plays came against) instead of the question's subject.
 */
import { tokenize } from "./resolvePlayers";
import { findTeams, type TeamMatch } from "./resolveTeams";

const LEADS = new Set(["against", "vs", "versus", "facing", "v"]);

/**
 * The teams named as opponents, their chips, and the words that name them (team, lead, "the"). With no
 * player named, a lone team after "against" is the question's subject ("passing yards against the
 * Chiefs" is the Chiefs' defense), so it is an opponent only next to another team.
 */
export function readOpponents(question: string, playerNamed: boolean): { teams: TeamMatch[]; filters: string[]; used: number[] } {
  const tokens = tokenize(question.replace(/%/g, " percent "));
  const teams: TeamMatch[] = [];
  const used: number[] = [];
  const named = findTeams(tokens);
  for (const team of named) {
    const the = tokens[team.start - 1] === "the" ? 1 : 0;
    const lead = team.start - 1 - the;
    if (LEADS.has(tokens[lead] ?? "")) {
      teams.push(team);
      for (let i = lead; i < team.start + team.length; i++) {
        used.push(i);
      }
    }
  }
  if (!playerNamed && teams.length === named.length) {
    return { teams: [], filters: [], used: [] };
  }
  return { teams, filters: [...new Set(teams.map((t) => `opp-${t.id}`))], used };
}
