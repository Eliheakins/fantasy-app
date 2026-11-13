import { isPending } from "@/api/envelope";
import { type Phase, isDone, phaseOf } from "@/features/effects/phase";
import { useLeagueApi, useLeagueRow } from "@/lib/league";
import { type Move, rankMoves, tradeMoves, waiverMoves } from "./moves";

export type MovesState = {
  addsPending: boolean;
  tradesPending: boolean;
  moves: Move[];
  /** Message when the free agent list failed. */
  addsError: string | null;
  tradesFailed: boolean;
  /** season: playoff odds; playoffs: title odds; out or over: no title left to play for, so there are no moves to rank. */
  phase: Phase;
};

/** Free agent adds (live, with Sleeper trending) and the stored trade ideas (my team only), in one ranked list. Each part reports its own state. */
export function useMoves(): MovesState {
  const adds = useLeagueApi("/api/leagues/{league}/waivers");
  const digest = useLeagueApi("/api/leagues/{league}/digest");
  const phase = phaseOf(useLeagueRow());
  const addMoves = adds.kind === "ready" ? waiverMoves(adds.data, phase) : [];
  const trades = digest.kind === "ready" ? tradeMoves(digest.data.trades, phase) : [];
  return {
    phase,
    addsPending: isPending(adds),
    tradesPending: isPending(digest),
    moves: isDone(phase) ? [] : rankMoves([...addMoves, ...trades]),
    addsError: adds.kind === "error" ? adds.error.message : adds.kind === "no_data" ? adds.message : null,
    tradesFailed: digest.kind === "error",
  };
}
