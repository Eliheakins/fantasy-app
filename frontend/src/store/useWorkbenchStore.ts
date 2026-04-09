import { create } from "zustand";

import { PLAYER_IDS_TOKEN } from "@/constants/formula";
import type { PbpShardInfo } from "@/lib/api";
import type { NFLPlayer } from "@/types/workbench";

export const MAX_PINNED_PLAYERS = 5;

/** Track A: play-by-play shards (`nfl_pbp_*`). */
export type FormulaLabTrack = "microscope" | "telescope";

const defaultFormulaMicroscope = `SELECT 
  SUM(yards_gained) AS total_yards,
  AVG(success) * 100 AS success_rate_pct
FROM nfl_pbp_2024
WHERE passer_player_id IN (${PLAYER_IDS_TOKEN})
  AND play_type = 'pass';`;

const defaultFormulaTelescope = `SELECT
  season,
  level,
  epa_per_play,
  total_yards,
  play_count
FROM gold_unified_performance
WHERE nfl_id IN (${PLAYER_IDS_TOKEN})
ORDER BY level DESC, season;`;

export interface WorkbenchState {
  activePlayer: NFLPlayer | null;
  /** Track A (Microscope): SQL against nfl_pbp_* views. */
  customFormula: string;
  /** Track B (Telescope): SQL against gold_unified_performance (+ player_hub mounted). */
  customFormulaTelescope: string;
  formulaLabTrack: FormulaLabTrack;
  isEngineReady: boolean;
  pinnedPlayers: NFLPlayer[];
  /** Shards last fetched per pinned player (gsis_id → shards). */
  playerShardMap: Record<string, PbpShardInfo[]>;
  setActivePlayer: (player: NFLPlayer | null) => void;
  setCustomFormula: (sql: string) => void;
  setCustomFormulaTelescope: (sql: string) => void;
  setFormulaLabTrack: (track: FormulaLabTrack) => void;
  setEngineReady: (ready: boolean) => void;
  /** Returns false if already pinned, at capacity, or duplicate. */
  tryPinPlayer: (player: NFLPlayer, shards: PbpShardInfo[]) => boolean;
  unpinPlayer: (gsisId: string) => void;
  clearPins: () => void;
}

export const useWorkbenchStore = create<WorkbenchState>((set, get) => ({
  activePlayer: null,
  customFormula: defaultFormulaMicroscope,
  customFormulaTelescope: defaultFormulaTelescope,
  formulaLabTrack: "microscope",
  isEngineReady: false,
  pinnedPlayers: [],
  playerShardMap: {},
  setActivePlayer: (player) => set({ activePlayer: player }),
  setCustomFormula: (sql) => set({ customFormula: sql }),
  setCustomFormulaTelescope: (sql) => set({ customFormulaTelescope: sql }),
  setFormulaLabTrack: (track) => set({ formulaLabTrack: track }),
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
