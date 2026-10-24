import type { Status } from "@/api/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ThemeSwitcher } from "./ThemeSwitcher";
import { useApi } from "@/hooks/useApi";
import { useLeague } from "@/lib/league";
import { formatAsOf, latestUpdate } from "@/lib/status";

export function TopBar() {
  const { leagues, league, setLeague } = useLeague();
  const status = useApi<Status>("/api/status");
  const updated = status.kind === "ready" ? latestUpdate(status.data) : null;
  const list = leagues.kind === "ready" ? leagues.data : [];
  return (
    <header className="flex min-h-14 items-center justify-between gap-2 border-b border-border px-4">
      <Select value={league ?? undefined} onValueChange={setLeague} disabled={list.length === 0}>
        <SelectTrigger aria-label="League" className="min-h-[44px] min-w-40">
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
      <div className="flex items-center gap-3">
        <ThemeSwitcher />
        <p className="text-caption text-muted">{updated ? `as of ${formatAsOf(updated)}` : "as of unknown"}</p>
      </div>
    </header>
  );
}
