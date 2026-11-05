import { useMemo } from "react";

import type { components } from "@/api/schema";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { useTeam } from "@/lib/teamContext";
import type { PlayerSet } from "@/stat/engine/statQuery";
import type { RosterFilter } from "@/stat/lib/queryUrl";

export type OwnerRow = components["schemas"]["OwnerRow"];
type OwnersData = components["schemas"]["OwnersData"];

/** The rostered players of the selected league and their owners, as the viewed team sees them (`?team=`). */
export function useLeagueOwners() {
  const { league } = useTeam();
  const state = useEnvelopeQuery<OwnersData>(league === null ? null : `/api/leagues/${encodeURIComponent(league)}/owners`);
  const rows = state.kind === "ready" ? state.data.rows : null;
  const unmatched = state.kind === "ready" ? state.data.unmatched : 0;
  const byPlayer = useMemo(() => (rows ? new Map(rows.map((r) => [r.gsis_id, r])) : null), [rows]);
  return { league, state, byPlayer, unmatched };
}

/** The players a League filter keeps: mine, everyone rostered, or (excluded) everyone rostered for free agents. */
export function playerSetFor(filter: RosterFilter, owners: readonly OwnerRow[]): PlayerSet {
  const mine = filter === "mine";
  return { ids: owners.filter((o) => !mine || o.is_mine).map((o) => o.gsis_id), exclude: filter === "fa" };
}
