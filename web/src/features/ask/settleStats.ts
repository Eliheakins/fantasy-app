import { familyDefault, familyMember, getStatById, isFamilyDefault, type PlayerRole } from "@/stat/config/statDictionary";

import { MAIN_ROLE } from "./ruleParser";

/** Who a question is about: a team, or players by position (empty for a ranking of everyone). */
export type StatSubject = { kind: "team" } | { kind: "players"; positions: readonly (string | null | undefined)[] };

/**
 * Generic words ("EPA", "success rate", "ADOT") name the passer's stat, the first of its family. Asked
 * about a team or a rusher or receiver, they mean that subject's own version, so the stat is swapped for
 * the family member that fits. A stat named by role ("rushing EPA") is kept as asked.
 */
export function settleStats(statIds: readonly string[], subject: StatSubject): string[] {
  const roles = new Set<PlayerRole>(
    subject.kind === "players" ? subject.positions.flatMap((p) => (p && MAIN_ROLE[p] ? [MAIN_ROLE[p]] : [])) : [],
  );
  const role = roles.size === 1 ? [...roles][0]! : null;
  const settled = statIds.map((id) => {
    const stat = getStatById(id);
    if (!stat?.family) {
      return id;
    }
    if (subject.kind === "team") {
      return isFamilyDefault(id) ? familyMember(id, "team") : id;
    }
    if (stat.teamOnly) {
      return role ? familyMember(id, role) : familyDefault(id);
    }
    return role && isFamilyDefault(id) ? familyMember(id, role) : id;
  });
  return [...new Set(settled)];
}
