import { create } from "zustand";

import type { NFLPlayer } from "@/shared/types/workbench";

export const MAX_PINNED_PLAYERS = 5;

export interface WorkbenchState {
  pinnedPlayers: NFLPlayer[];
  /** Returns false if already pinned or at capacity. */
  tryPinPlayer: (player: NFLPlayer) => boolean;
  /** Replace every pin at once (Ask); duplicates are dropped and the list is capped. */
  setPins: (players: NFLPlayer[]) => void;
  unpinPlayer: (gsisId: string) => void;
  clearPins: () => void;
}

export const useWorkbenchStore = create<WorkbenchState>((set, get) => ({
  pinnedPlayers: [],

  tryPinPlayer: (player) => {
    const { pinnedPlayers } = get();
    if (pinnedPlayers.length >= MAX_PINNED_PLAYERS) {
      return false;
    }
    if (pinnedPlayers.some((p) => p.gsis_id === player.gsis_id)) {
      return false;
    }
    set({ pinnedPlayers: [...pinnedPlayers, player] });
    return true;
  },

  setPins: (players) => {
    const unique = [...new Map(players.map((p) => [p.gsis_id, p])).values()];
    set({ pinnedPlayers: unique.slice(0, MAX_PINNED_PLAYERS) });
  },

  unpinPlayer: (gsisId) => set({ pinnedPlayers: get().pinnedPlayers.filter((p) => p.gsis_id !== gsisId) }),

  clearPins: () => set({ pinnedPlayers: [] }),
}));
