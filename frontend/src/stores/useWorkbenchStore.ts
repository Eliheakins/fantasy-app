import { create } from "zustand";

import type { PbpShardInfo } from "@/shared/lib/api";
import type { NFLPlayer } from "@/shared/types/workbench";

export const MAX_PINNED_PLAYERS = 5;

export interface PinEntry {
  player: NFLPlayer;
  shards: PbpShardInfo[];
}

export interface WorkbenchState {
  isEngineReady: boolean;
  pinnedPlayers: NFLPlayer[];
  /** Shards last fetched per pinned player (gsis_id → shards). */
  playerShardMap: Record<string, PbpShardInfo[]>;
  setEngineReady: (ready: boolean) => void;
  /** Returns false if already pinned, at capacity, or duplicate. */
  tryPinPlayer: (player: NFLPlayer, shards: PbpShardInfo[]) => boolean;
  /** Replace every pin at once (Ask); duplicates are dropped and the list is capped. */
  setPins: (entries: PinEntry[]) => void;
  unpinPlayer: (gsisId: string) => void;
  clearPins: () => void;
}

export const useWorkbenchStore = create<WorkbenchState>((set, get) => ({
  isEngineReady: false,
  pinnedPlayers: [],
  playerShardMap: {},
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
    });
    return true;
  },

  setPins: (entries) => {
    const unique = [...new Map(entries.map((e) => [e.player.gsis_id, e])).values()].slice(
      0,
      MAX_PINNED_PLAYERS,
    );
    set({
      pinnedPlayers: unique.map((e) => e.player),
      playerShardMap: Object.fromEntries(unique.map((e) => [e.player.gsis_id, e.shards])),
    });
  },

  unpinPlayer: (gsisId) => {
    const { pinnedPlayers, playerShardMap } = get();
    const { [gsisId]: _removed, ...restMap } = playerShardMap;
    set({
      pinnedPlayers: pinnedPlayers.filter((p) => p.gsis_id !== gsisId),
      playerShardMap: restMap,
    });
  },

  clearPins: () =>
    set({
      pinnedPlayers: [],
      playerShardMap: {},
    }),
}));
