import { parseRules, type RuleResult } from "../ruleParser";
import { matchesFor } from "./matches";
import { showRules } from "./queryStates";
import type { AskPath } from "./types";

/** A question that names no player: a league ranking or a team question the rules read, or a refusal they are sure of. */
export const rulesPath: AskPath<RuleResult> = {
  id: "rules",
  read: (input) => {
    const matches = matchesFor(input);
    if (matches.length > 0) return null;
    const read = parseRules(input.question, {
      matches,
      seasons: input.seasons,
      chipGroups: input.chipGroups,
      maxWeeks: input.maxWeeks,
    });
    // A ranking or team question the rules could not finish goes to the model, which can rank too.
    return read.status === "resolved" || read.status === "unsupported" ? read : null;
  },
  answer: (read, { question, seasons, maxWeeks }, actions) => {
    if (read.status === "resolved") {
      showRules(read.intent, read.leaderboard, read.team, question, actions, { seasons, maxWeeks });
      return;
    }
    actions.fail(question, "none", read.reason);
  },
};
