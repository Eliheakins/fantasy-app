import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import type { Status } from "@/api/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi } from "@/hooks/useApi";
import { useLeague } from "@/lib/league";
import { WEEK_PATHS } from "@/nav";
import { useWeek } from "@/lib/week";
import { FIRST_WEEK, LAST_WEEK } from "@/features/scoreboard/logic";
import { useTeam } from "@/lib/teamContext";
import { formatAsOf, latestUpdate, liveLabel } from "@/lib/status";
import { AskBox } from "./AskBox";

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

const WEEKS = Array.from({ length: LAST_WEEK - FIRST_WEEK + 1 }, (_, i) => i + FIRST_WEEK);
/** Selects on the forest band: a translucent pill, white text, 44 px high. */
const PILL = "min-h-[44px] w-full border-white/25 bg-white/10 text-white hover:bg-white/15 md:w-auto md:min-w-32 [&_svg]:text-white";

/** The forest band: team name over "Updated …", league, team and week selects, and the Ask field. */
export function TopBar() {
  const now = useNow();
  const { leagues, league, setLeague } = useLeague();
  const { team, teams, setTeam } = useTeam();
  const { week, setWeek } = useWeek();
  const { pathname } = useLocation();
  const followsWeek = WEEK_PATHS.includes(pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname);
  const weekReady = leagues.kind === "ready";
  const mine = teams.find((t) => t.is_me)?.roster_id ?? null;
  const shown = teams.find((t) => t.roster_id === (team ?? mine));
  const status = useApi<Status>("/api/status");
  const updated = status.kind === "ready" ? latestUpdate(status.data) : null;
  const live = status.kind === "ready" ? liveLabel(status.data, now) : null;
  const list = leagues.kind === "ready" ? leagues.data : [];
  return (
    <header className="on-chrome bg-[#123D2C] text-white">
      <div className="mx-auto flex w-full max-w-[1200px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <div className="min-w-0 flex-1 md:flex-none">
          <p className="truncate font-display text-[22px] font-medium leading-7">{shown?.team_name ?? "Fantasy"}</p>
          <p className="min-h-4 text-caption text-[#9CC7B2]">
            {status.kind === "ready" ? (live ?? `Updated ${updated ? formatAsOf(updated) : "unknown"}`) : null}
          </p>
        </div>
        <div className="order-last grid w-full grid-cols-3 gap-2 md:order-none md:ml-auto md:flex md:w-auto">
          <Select value={league ?? ""} onValueChange={(key) => {
              setLeague(key);
              setTeam(null); // roster ids belong to one league
            }} disabled={list.length === 0}>
            <SelectTrigger aria-label="Choose league" className={PILL}>
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
            <SelectTrigger aria-label="View team" className={PILL}>
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
          <Select value={weekReady ? String(week) : ""} onValueChange={(w) => setWeek(Number(w))} disabled={!weekReady || !followsWeek}>
            <SelectTrigger
              aria-label="Choose week"
              title={followsWeek ? undefined : "This page shows the current week"}
              aria-description={followsWeek ? undefined : "This page shows the current week"}
              className={PILL}
            >
              <SelectValue placeholder="Week" />
            </SelectTrigger>
            <SelectContent>
              {WEEKS.map((w) => (
                <SelectItem key={w} value={String(w)}>
                  Week {w}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <AskBox />
      </div>
    </header>
  );
}
