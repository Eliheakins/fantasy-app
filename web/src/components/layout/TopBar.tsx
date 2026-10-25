import { useEffect, useState } from "react";
import type { Status } from "@/api/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi } from "@/hooks/useApi";
import { useLeague } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";
import { formatAsOf, latestUpdate, liveLabel } from "@/lib/status";

const LIVE_TICK_MS = 30_000;

/** Current time, refreshed so the "updated N min ago" label keeps moving. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), LIVE_TICK_MS);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

export function TopBar() {
  const now = useNow();
  const { leagues, league, setLeague } = useLeague();
  const { team, teams, setTeam } = useTeam();
  const mine = teams.find((t) => t.is_me)?.roster_id ?? null;
  const status = useApi<Status>("/api/status");
  const updated = status.kind === "ready" ? latestUpdate(status.data) : null;
  const live = status.kind === "ready" ? liveLabel(status.data, now) : null;
  const list = leagues.kind === "ready" ? leagues.data : [];
  return (
    <header className="grid grid-cols-2 items-center gap-2 border-b border-border px-4 py-2 md:flex md:min-h-14 md:flex-wrap md:justify-between">
      <Select value={league ?? undefined} onValueChange={(key) => {
          setLeague(key);
          setTeam(null); // roster ids belong to one league
        }} disabled={list.length === 0}>
        <SelectTrigger aria-label="Choose league" className="min-h-[44px] w-full md:w-auto md:min-w-40">
          <SelectValue placeholder="No leagues" />
        </SelectTrigger>
        <SelectContent>
          {list.map((l) => (
            <SelectItem key={l.league_key} value={l.league_key}>
              {l.name ?? l.league_key}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={String(team ?? mine ?? "")}
        onValueChange={(id) => setTeam(Number(id) === mine ? null : Number(id))}
        disabled={teams.length === 0}
      >
        <SelectTrigger aria-label="View team" className="min-h-[44px] w-full md:w-auto md:min-w-40">
          <SelectValue placeholder="Team" />
        </SelectTrigger>
        <SelectContent>
          {teams.map((t) => (
            <SelectItem key={t.roster_id} value={String(t.roster_id)}>
              {t.team_name ?? `Team ${t.roster_id}`}
              {t.is_me ? " (My team)" : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="col-span-2 text-caption text-muted">{live ?? (updated ? `as of ${formatAsOf(updated)}` : "as of unknown")}</p>
    </header>
  );
}
