import { isPending } from "@/api/envelope";
import type { DigestData } from "@/lib/digestTypes";
import type { WaiverRow } from "@/features/moves/waivers/logic";
import { type Phase, phaseOf } from "@/features/effects/phase";
import { useLeague, useLeagueApi } from "@/lib/league";
import { type Move, rankMoves, tradeMoves, waiverMoves } from "./moves";

export type MovesState = {
  addsPending: boolean;
  tradesPending: boolean;
  moves: Move[];
  /** Message when the free agent list failed. */
  addsError: string | null;
  tradesFailed: boolean;
  /** season: playoff odds; playoffs: title odds; out: my team cannot win the title, so there are no moves to rank. */
  phase: Phase;
};

/** Free agent adds (live, with Sleeper trending) and the stored trade ideas (my team only), in one ranked list. Each part reports its own state. */
export function useMoves(): MovesState {
  const adds = useLeagueApi<WaiverRow[]>("waivers");
  const digest = useLeagueApi<DigestData>("digest");
  const { league, leagues } = useLeague();
  const row = leagues.kind === "ready" ? leagues.data.find((l) => l.league_key === league) : undefined;
  const phase = phaseOf(row, digest.kind === "ready" ? digest.data.odds_change : []);
  const addMoves = adds.kind === "ready" ? waiverMoves(adds.data, phase) : [];
  const trades = digest.kind === "ready" ? tradeMoves(digest.data.trades, phase) : [];
  return {
    phase,
    addsPending: isPending(adds),
    tradesPending: isPending(digest),
    moves: phase === "out" ? [] : rankMoves([...addMoves, ...trades]),
    addsError: adds.kind === "error" ? adds.error.message : adds.kind === "no_data" ? adds.message : null,
    tradesFailed: digest.kind === "error",
  };
}
