import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getPlayers, searchPlayers } from "@/shared/lib/players";
import type { NFLPlayer } from "@/shared/types/workbench";
import { MAX_PINNED_PLAYERS, useWorkbenchStore } from "@/stores/useWorkbenchStore";

export function useExplorePlayerSearch() {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [pinMessage, setPinMessage] = useState<string | null>(null);

  const pinnedPlayers = useWorkbenchStore((s) => s.pinnedPlayers);
  const tryPinPlayer = useWorkbenchStore((s) => s.tryPinPlayer);

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  const searchQ = useQuery({
    queryKey: ["search", debounced],
    queryFn: async () => searchPlayers(await getPlayers(), debounced),
    enabled: debounced.trim().length >= 2,
  });

  const onSelectPlayer = useCallback(
    (p: NFLPlayer) => {
      setPinMessage(null);
      if (pinnedPlayers.some((x) => x.gsis_id === p.gsis_id)) {
        setPinMessage("Already pinned.");
        return;
      }
      if (pinnedPlayers.length >= MAX_PINNED_PLAYERS) {
        setPinMessage(`You can pin at most ${MAX_PINNED_PLAYERS} players.`);
        return;
      }

      if (tryPinPlayer(p)) {
        setQuery("");
      } else {
        setPinMessage("Could not pin (duplicate or limit).");
      }
    },
    [pinnedPlayers, tryPinPlayer],
  );

  const suggestions = useMemo(() => searchQ.data ?? [], [searchQ.data]);

  const isPinned = useCallback(
    (gsisId: string) => pinnedPlayers.some((p) => p.gsis_id === gsisId),
    [pinnedPlayers],
  );

  return {
    query,
    setQuery,
    debounced,
    suggestions,
    isPinned,
    pinnedPlayers,
    onSelectPlayer,
    pinMessage,
  };
}
