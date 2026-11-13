import { useState } from "react";
import type { SleeperTeam } from "@/api/types";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Props = {
  leagueId: string;
  leagueName: string;
  /** The team to start on: the one already picked, or else the one this Sleeper user owns. */
  initial: number | null;
  ownerId?: string;
  confirmLabel: string;
  isBusy: boolean;
  onConfirm: (rosterId: number) => void;
  onCancel: () => void;
};

const teamLabel = (t: SleeperTeam) => (t.owner_name && t.owner_name !== t.team_name ? `${t.team_name} (${t.owner_name})` : t.team_name);

/** Pick which team in a league is yours. The app views that team as "me" in the league. */
export function TeamPicker({ leagueId, leagueName, initial, ownerId, confirmLabel, isBusy, onConfirm, onCancel }: Props) {
  const state = useEnvelopeQuery("/api/me/sleeper/leagues/{league_id}/teams", { path: { league_id: leagueId } });
  const [picked, setPicked] = useState<number | null>(null);
  const labelId = `team-label-${leagueId}`;
  return (
    <div className="mt-2 flex w-full flex-col gap-2 rounded-md border border-line bg-panel p-3">
      <ApiBoundary state={state}>
        {(teams) => {
          const owned = teams.find((t) => ownerId !== undefined && t.owner_id === ownerId)?.roster_id ?? null;
          const chosen = picked ?? initial ?? owned;
          return (
            <>
              <span id={labelId} className="text-body font-medium text-ink">
                Which team in {leagueName} is yours?
              </span>
              <Select value={chosen === null ? undefined : String(chosen)} onValueChange={(v) => setPicked(Number(v))}>
                <SelectTrigger aria-labelledby={labelId} className="w-full sm:w-80">
                  <SelectValue placeholder="Choose your team" />
                </SelectTrigger>
                <SelectContent>
                  {teams.map((t) => (
                    <SelectItem key={t.roster_id} value={String(t.roster_id)}>
                      {teamLabel(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="flex gap-2">
                <Button size="sm" disabled={chosen === null || isBusy} onClick={() => chosen !== null && onConfirm(chosen)}>
                  {isBusy ? "Saving…" : confirmLabel}
                </Button>
                <Button size="sm" variant="outline" onClick={onCancel}>
                  Cancel
                </Button>
              </span>
            </>
          );
        }}
      </ApiBoundary>
    </div>
  );
}
