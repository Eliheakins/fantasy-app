import { useQuery } from "@tanstack/react-query";
import { type ApiState, fetchEnvelope, pollInterval, resolveState } from "@/api/envelope";
import type { Envelope } from "@/api/types";
import { withTeam } from "@/lib/team";
import { useTeam } from "@/lib/teamContext";

/** GET an /api route, as the viewed team when one is chosen. Polls every 2 s while the server says "running". */
export function useApi<T>(path: string | null): ApiState<T> {
  const { team, league } = useTeam();
  const url = path === null ? null : withTeam(path, team, league); // so the team is part of the query key
  const query = useQuery<Envelope<T>, Error>({
    queryKey: ["api", url],
    queryFn: () => fetchEnvelope<T>(url ?? ""),
    enabled: url !== null,
    refetchInterval: (q) => (q.state.error ? false : pollInterval(q.state.data)),
    retry: 1,
  });
  if (url === null) return { kind: "loading" };
  const state = resolveState(query.data, query.error);
  return state.kind === "error" ? { ...state, retry: () => void query.refetch() } : state;
}
