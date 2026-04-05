import { create } from "zustand";

import { PLAYER_IDS_TOKEN } from "@/constants/formula";
import type { PbpShardInfo } from "@/lib/api";
import type { NFLPlayer } from "@/types/workbench";

export const MAX_PINNED_PLAYERS = 5;

const defaultFormula = `SELECT 
  SUM(yards_gained) AS total_yards,
  AVG(success) * 100 AS success_rate_pct
FROM nfl_pbp_2024
WHERE passer_player_id IN (${PLAYER_IDS_TOKEN})
  AND play_type = 'pass';`;

export interface WorkbenchState {
  activePlayer: NFLPlayer | null;
  customFormula: string;
  isEngineReady: boolean;
  pinnedPlayers: NFLPlayer[];
  /** Shards last fetched per pinned player (gsis_id → shards). */
  playerShardMap: Record<string, PbpShardInfo[]>;
  setActivePlayer: (player: NFLPlayer | null) => void;
  setCustomFormula: (sql: string) => void;
  setEngineReady: (ready: boolean) => void;
  /** Returns false if already pinned, at capacity, or duplicate. */
  tryPinPlayer: (player: NFLPlayer, shards: PbpShardInfo[]) => boolean;
  unpinPlayer: (gsisId: string) => void;
  clearPins: () => void;
}

export const useWorkbenchStore = create<WorkbenchState>((set, get) => ({
  activePlayer: null,
  customFormula: defaultFormula,
  isEngineReady: false,
  pinnedPlayers: [],
  playerShardMap: {},
  setActivePlayer: (player) => set({ activePlayer: player }),
  setCustomFormula: (sql) => set({ customFormula: sql }),
  setEngineReady: (ready) => set({ isEngineReady: ready }),

  tryPinPlayer: (player, shards) => {
    const { pinnedPlayers, playerShardMap } = get();
    if (pinnedPlayers.length >= MAX_PINNED_PLAYERS) {
      return false;
    }
    if (pinnedPlayers.some((p) => p.gsis_id === player.gsis_id)) {
      return false;
    }
    set({
      pinnedPlayers: [...pinnedPlayers, player],
      playerShardMap: { ...playerShardMap, [player.gsis_id]: shards },
      activePlayer: player,
    });
    return true;
  },

  unpinPlayer: (gsisId) => {
    const { pinnedPlayers, playerShardMap, activePlayer } = get();
    const { [gsisId]: _removed, ...restMap } = playerShardMap;
    const nextPinned = pinnedPlayers.filter((p) => p.gsis_id !== gsisId);
    set({
      pinnedPlayers: nextPinned,
      playerShardMap: restMap,
      activePlayer: activePlayer?.gsis_id === gsisId ? nextPinned[nextPinned.length - 1] ?? null : activePlayer,
    });
  },

  clearPins: () =>
    set({
      pinnedPlayers: [],
      playerShardMap: {},
      activePlayer: null,
    }),
}));
