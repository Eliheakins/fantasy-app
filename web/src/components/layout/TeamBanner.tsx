import { useTeam } from "@/lib/teamContext";

/** Shown only for a team other than mine, so a screenshot is never misread as the owner's view. */
export function TeamBanner() {
  const { viewed, setTeam } = useTeam();
  return (
    <div aria-live="polite" role="status">
      {viewed && (
        <p className="flex flex-wrap items-center gap-x-3 border-b border-border bg-surface px-4 py-2 text-body text-muted">
          <span>Viewing as {viewed.team_name ?? `Team ${viewed.roster_id}`}</span>
          <button type="button" onClick={() => setTeam(null)} className="min-h-[44px] underline">
            Back to my team
          </button>
        </p>
      )}
    </div>
  );
}
