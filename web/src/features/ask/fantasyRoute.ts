/**
 * Fantasy questions the stat engine does not answer but the app does: injuries, projections and the
 * rest of the season, waivers and drops, byes and this week's games. Read by rules alone, before the
 * stat paths, so the question never reaches the model and the answer is a link to the page that has it
 * (league data stays in the app).
 */
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";

import { resolvePlayers } from "./resolvePlayers";
import { dropTeamNames, resolveTeams } from "./resolveTeams";

/** Where a fantasy question is answered: a page in the app (path and query), or only a message. */
export interface FantasyRoute {
  text: string;
  /** App path with its own query ("/moves?view=fa"); null when no page has it. */
  to: string | null;
  label: string | null;
}

const WAIVERS = /\bwaivers?\b|\bwaiver wire\b|\bpick ?up\b|\bwho (?:should i|to|can i) add\b/;
const FREE_AGENTS = /\bfree[- ]agents?\b/;
/** A count the stat paths answer ("free agent WRs with the most targets"); "best" and "top" stay Moves' ranking. */
const STAT_COUNT = /\b(?:most|fewest|least|highest|lowest)\b/;
const DROPS = /\bwho (?:should i|to|do i) (?:drop|cut|release)\b|\bshould i (?:drop|cut|release)\b/;
const INJURY = /\binjur(?:ed|y|ies)\b|\bhurt\b|\bhealthy\b|\bquestionable\b|\bdoubtful\b|\binjury report\b/;
const PROJECTION = /\bproject(?:ed|ion|ions)\b|\brest of (?:the )?season\b|\bros\b|\boutlook\b/;
const THIS_WEEK = /\bbye\b|\bwho (?:does|do|is) .+ (?:play|playing|facing)\b|\bopponent this week\b|\bmatchup this week\b/;
const SCHEDULE = /\b(?:easiest|hardest|toughest|weakest) (?:remaining )?schedules?\b|\bstrength of schedule\b/;

/** The one player a question names, when it names exactly one and the name has one skill-position match. */
function onePlayer(question: string, dictionary: readonly PlayerDictionaryRow[]): PlayerDictionaryRow | null {
  const matches = dropTeamNames(resolvePlayers(question, dictionary), resolveTeams(question));
  if (matches.length !== 1) {
    return null;
  }
  const skill = matches[0]!.candidates.filter((c) => ["QB", "RB", "WR", "TE", "FB"].includes(c.position ?? ""));
  return skill.length === 1 ? skill[0]! : null;
}

/** The page a fantasy question belongs on, or null when it is a stat question for the other paths. */
export function readFantasyRoute(question: string, dictionary: readonly PlayerDictionaryRow[]): FantasyRoute | null {
  const q = question.toLowerCase();
  if (WAIVERS.test(q) || DROPS.test(q) || (FREE_AGENTS.test(q) && !STAT_COUNT.test(q))) {
    return {
      text: "Who to add, and whom to drop for them, is on the Moves page, ranked by what each move does to your season.",
      to: "/moves?view=fa",
      label: "Moves: free agents",
    };
  }
  if (SCHEDULE.test(q)) {
    return { text: "Strength of schedule is not in the app yet.", to: null, label: null };
  }
  const asksInjury = INJURY.test(q);
  const asksProjection = PROJECTION.test(q);
  if (asksInjury || asksProjection) {
    const player = onePlayer(question, dictionary);
    if (player) {
      return {
        text: `${player.display_name}'s ${asksInjury ? "injury status and next game range" : "next game range and rest-of-season value"} are on his player page.`,
        to: `/players/${encodeURIComponent(player.gsis_id)}`,
        label: player.display_name,
      };
    }
    return asksProjection
      ? { text: "This week's projections for your lineup are on the Lineup page.", to: "/lineup", label: "Lineup" }
      : { text: "Name one player to see his injury status on his player page.", to: null, label: null };
  }
  if (THIS_WEEK.test(q)) {
    return { text: "This week's games, and who is on bye, are on the Lineup page.", to: "/lineup", label: "Lineup" };
  }
  return null;
}
