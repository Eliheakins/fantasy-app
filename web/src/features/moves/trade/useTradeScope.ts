import { useLeague } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";

/** League and viewed team; drafts and finder results belong to one team. */
export function useTradeScope() {
  const { league } = useLeague();
  const { team } = useTeam();
  return { league, scope: `${league}:${team ?? "mine"}` };
}
