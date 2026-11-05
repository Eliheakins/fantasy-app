import { parseRules, type RuleResult } from "../ruleParser";
import { matchesFor } from "./matches";
import { showRules } from "./queryStates";
import type { AskPath } from "./types";

const NO_PLAYER_MESSAGE =
  "I couldn't find a player or team in that question. Name a player by last or full name, like " +
  "“Mahomes passing yards 2023”, a team, like “Chiefs passing yards 2023”, or ask for a leaderboard like " +
  "“who led the league in passing yards in 2023”.";

/** A question that names no player: a league ranking or a team question the rules read, else a reason why not. */
export const rulesPath: AskPath<RuleResult> = {
  id: "rules",
  read: (input) => {
    const matches = matchesFor(input);
    if (matches.length > 0) return null;
    return parseRules(input.question, { matches, seasons: input.seasons, chipGroups: input.chipGroups });
  },
  answer: (read, { question }, actions) => {
    if (read.status === "resolved" && (read.leaderboard || read.team)) {
      showRules(read.intent, read.leaderboard, read.team, question, actions);
      return;
    }
    // With no player, "ambiguous" is a ranking question the rules could not finish: say why.
    const text = read.status === "unsupported" || read.status === "ambiguous" ? read.reason : NO_PLAYER_MESSAGE;
    actions.fail(question, "none", text);
  },
};
