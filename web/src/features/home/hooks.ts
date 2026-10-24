import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiFailure, fetchEnvelope } from "@/api/envelope";
import type { League } from "@/api/types";
import type { ApiState } from "@/api/envelope";
import { useApi } from "@/hooks/useApi";

/** Every league from /api/leagues, independent of the top-bar picker. */
export function useHomeLeagues(): ApiState<League[]> {
  return useApi<League[]>("/api/leagues");
}

export const leagueUrl = (key: string, path: string) =>
  `/api/leagues/${encodeURIComponent(key)}/${path}`;

/** POST /api/live/refresh, then refetch everything. */
export function useRefreshScores() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const env = await fetchEnvelope<{ player_rows: number }>("/api/live/refresh", { method: "POST" });
      if (env.status !== "ok") throw new ApiFailure(env.error?.message ?? "Refresh failed", env.error?.code);
      return env.data;
    },
    onSuccess: () => client.invalidateQueries({ predicate: (q) => q.queryKey[0] === "api" }), // keep ["post", ...] trade results
  });
}
