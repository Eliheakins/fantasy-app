import { afterEach, describe, expect, it } from "vitest";

import type { NFLPlayer } from "@/shared/types/workbench";

import { MAX_PINNED_PLAYERS, useWorkbenchStore } from "./useWorkbenchStore";

const player = (id: string): NFLPlayer => ({
  gsis_id: id,
  full_name: `Player ${id}`,
  position: "QB",
  team: "KC",
  headshot_url: null,
});

afterEach(() => {
  useWorkbenchStore.getState().clearPins();
});

describe("pinned players", () => {
  it("pins a player once and refuses a duplicate", () => {
    const { tryPinPlayer } = useWorkbenchStore.getState();

    expect(tryPinPlayer(player("a"))).toBe(true);
    expect(tryPinPlayer(player("a"))).toBe(false);
    expect(useWorkbenchStore.getState().pinnedPlayers).toHaveLength(1);
  });

  it("stops at the pin limit", () => {
    const { tryPinPlayer } = useWorkbenchStore.getState();
    for (let i = 0; i < MAX_PINNED_PLAYERS; i++) {
      expect(tryPinPlayer(player(String(i)))).toBe(true);
    }

    expect(tryPinPlayer(player("extra"))).toBe(false);
  });

  it("replaces every pin at once, dropping duplicates and capping the list", () => {
    const ids = ["a", "b", "a", "c", "d", "e", "f", "g"];

    useWorkbenchStore.getState().setPins(ids.map(player));

    expect(useWorkbenchStore.getState().pinnedPlayers.map((p) => p.gsis_id)).toEqual(["a", "b", "c", "d", "e"]);
  });

  it("unpins one player and clears all", () => {
    const store = useWorkbenchStore.getState();
    store.setPins([player("a"), player("b")]);

    store.unpinPlayer("a");
    expect(useWorkbenchStore.getState().pinnedPlayers.map((p) => p.gsis_id)).toEqual(["b"]);

    store.clearPins();
    expect(useWorkbenchStore.getState().pinnedPlayers).toEqual([]);
  });
});
