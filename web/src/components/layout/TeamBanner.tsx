import { useTeam } from "@/lib/teamContext";

const STRIP = "flex min-h-[44px] flex-wrap items-center gap-x-3 border-b border-l-4 border-line border-l-focus bg-panel px-4 text-body";
const ACTION = "min-h-[44px] underline";

/** Sticky strip on phones, so a scrolled screenshot is never misread as the owner's view (from 768 px up the
 * sticky header's team name and team select say it): it names the viewed team,
 * or explains that a link named a team that is not in this league. */
export function TeamBanner() {
  const { viewed, setTeam, notice, dismissNotice } = useTeam();
  return (
    <div aria-live="polite" role="status" className="sticky top-0 z-20 md:static">
      {viewed && (
        <p className={STRIP}>
          <span>Viewing as {viewed.team_name ?? `Team ${viewed.roster_id}`}</span>
          <button type="button" onClick={() => setTeam(null)} className={ACTION}>
            Back to my team
          </button>
        </p>
      )}
      {!viewed && notice && (
        <p className={STRIP}>
          <span>{notice}</span>
          <button type="button" onClick={dismissNotice} className={ACTION}>
            Dismiss
          </button>
        </p>
      )}
    </div>
  );
}
