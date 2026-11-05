import type { ApiState } from "@/api/envelope";
import type { DigestData } from "@/features/digest/types";
import type { WaiverRow } from "@/features/waivers/logic";
import { useLeagueApi } from "@/lib/league";
import { type Move, rankMoves, tradeMoves, waiverMoves } from "./moves";

const isOpen = (s: ApiState<unknown>) => s.kind === "loading" || s.kind === "running";

export type MovesState = {
  pending: boolean;
  moves: Move[];
  /** Message when the free agent list failed: then there is no answer to give. */
  addsError: string | null;
  tradesFailed: boolean;
};

/** Free agent adds (live, with Sleeper trending) and the stored trade ideas (my team only), in one ranked list. */
export function useMoves(): MovesState {
  const adds = useLeagueApi<WaiverRow[]>("waivers");
  const digest = useLeagueApi<DigestData>("digest");
  const addMoves = adds.kind === "ready" ? waiverMoves(adds.data) : [];
  const trades = digest.kind === "ready" ? tradeMoves(digest.data.trades) : [];
  return {
    pending: isOpen(adds) || isOpen(digest),
    moves: rankMoves([...addMoves, ...trades]),
    addsError: adds.kind === "error" ? adds.error.message : adds.kind === "no_data" ? adds.message : null,
    tradesFailed: digest.kind === "error",
  };
}
