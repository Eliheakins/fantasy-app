import type { ApiState } from "@/api/envelope";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { useTeam } from "@/lib/teamContext";
import type { PlayerProfile } from "./profile";

const PROFILE = "/api/leagues/{league}/players/{gsis_id}/profile";

/** The player's next game range, rest of season over replacement, injury and outlook for the selected league. */
export function useProfile(gsisId: string): ApiState<PlayerProfile> {
  const { league } = useTeam();
  return useEnvelopeQuery(PROFILE, league === null ? null : { path: { league, gsis_id: gsisId } });
}

/** Profiles of up to MAX_COMPARE players, in order; the same queries the columns make, so nothing is fetched twice. */
export function useProfiles(gsisIds: readonly string[]): ApiState<PlayerProfile>[] {
  const { league } = useTeam();
  const params = (i: number) => {
    const id = gsisIds[i];
    return league === null || id === undefined ? null : { path: { league, gsis_id: id } };
  };
  const states = [useEnvelopeQuery(PROFILE, params(0)), useEnvelopeQuery(PROFILE, params(1)), useEnvelopeQuery(PROFILE, params(2))];
  return states.slice(0, gsisIds.length);
}
