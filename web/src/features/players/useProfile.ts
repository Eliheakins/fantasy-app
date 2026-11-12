import type { ApiState } from "@/api/envelope";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { leagueUrl } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";
import type { PlayerProfile } from "./profile";

/** A GET under /api/leagues/<league>/ for the selected league; loading until a league is chosen. */
export function useLeaguePath<T>(path: string): ApiState<T> {
  const { league } = useTeam();
  return useEnvelopeQuery<T>(league === null ? null : leagueUrl(league, path));
}

const profilePath = (gsisId: string) => `players/${encodeURIComponent(gsisId)}/profile`;

/** The player's next game range, rest of season over replacement, injury and outlook for the selected league. */
export function useProfile(gsisId: string): ApiState<PlayerProfile> {
  return useLeaguePath<PlayerProfile>(profilePath(gsisId));
}

/** Profiles of up to MAX_COMPARE players, in order; the same queries the columns make, so nothing is fetched twice. */
export function useProfiles(gsisIds: readonly string[]): ApiState<PlayerProfile>[] {
  const { league } = useTeam();
  const path = (i: number) => {
    const id = gsisIds[i];
    return league === null || id === undefined ? null : leagueUrl(league, profilePath(id));
  };
  const states = [
    useEnvelopeQuery<PlayerProfile>(path(0)),
    useEnvelopeQuery<PlayerProfile>(path(1)),
    useEnvelopeQuery<PlayerProfile>(path(2)),
  ];
  return states.slice(0, gsisIds.length);
}
