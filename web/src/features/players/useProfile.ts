import type { ApiState } from "@/api/envelope";
import { useApi } from "@/hooks/useApi";
import { useTeam } from "@/lib/teamContext";
import type { PlayerProfile } from "./profile";

/** A GET under /api/leagues/<league>/ for the selected league; loading until a league is chosen. */
export function useLeaguePath<T>(path: string): ApiState<T> {
  const { league } = useTeam();
  return useApi<T>(league === null ? null : `/api/leagues/${encodeURIComponent(league)}/${path}`);
}

/** The player's next game range, rest of season over replacement, injury and outlook for the selected league. */
export function useProfile(gsisId: string): ApiState<PlayerProfile> {
  return useLeaguePath<PlayerProfile>(`players/${encodeURIComponent(gsisId)}/profile`);
}
