import { useEffect } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { navSearch } from "@/components/layout/navLinks";
import { PageHeader } from "@/components/PageHeader";
import { PlayerPicker } from "@/features/players/PlayerPicker";
import { PlayerSections } from "@/features/players/PlayerSections";
import { MAX_COMPARE, parseCompareIds, withoutPlayer, withPlayer } from "@/features/players/profile";
import { usePlayer } from "@/features/players/usePlayer";

const GRID_BY_COUNT: Record<number, string> = { 1: "md:grid-cols-1", 2: "md:grid-cols-2", 3: "md:grid-cols-3" };

function Column({ gsisId, onRemove }: { gsisId: string; onRemove: () => void }) {
  const { pathname, search } = useLocation();
  const player = usePlayer(gsisId);
  const info = player.kind === "ready" ? player.data : null;
  const unknown = player.kind === "ready" && info === null;
  const name = unknown ? "Player not found" : (info?.full_name ?? gsisId);
  return (
    <div role="group" aria-label={name} className="min-w-0 space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-section font-semibold">
          {unknown ? name : (
            <Link to={{ pathname: `/players/${encodeURIComponent(gsisId)}`, search: navSearch("/players/:gsisId", search, pathname) }} className="inline-flex min-h-[44px] items-center underline">
              {name}
            </Link>
          )}
        </h2>
        <button type="button" aria-label={`Remove ${name}`} onClick={onRemove} className="min-h-[44px] px-3 text-body text-muted underline">
          Remove
        </button>
      </div>
      {unknown && <p className="text-body text-muted">No player in the stat data has the id {gsisId}.</p>}
      {info && <p className="text-caption uppercase tracking-wide text-muted">{[info.position, info.team].filter(Boolean).join(" · ")}</p>}
      {info && <PlayerSections gsisId={gsisId} level={3} name={name} />}
    </div>
  );
}

/** Two or three players side by side with the player page's sections; the ids live in repeated ?p= params. */
export default function PlayersCompare() {
  const [params, setParams] = useSearchParams();
  const ids = parseCompareIds(params);
  const setIds = (next: string[], replace = false) =>
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev);
        out.delete("p");
        next.forEach((id) => out.append("p", id));
        return out;
      },
      { replace },
    );
  // A hand-edited URL with repeats, blanks or more than three ids is rewritten to what the page shows.
  const raw = params.getAll("p").join("\n");
  useEffect(() => {
    if (raw !== "" && raw !== ids.join("\n")) setIds(ids, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raw]);
  return (
    <div className="space-y-6">
      <PageHeader
        title="Compare players"
        eyebrow="Players"
        answer={ids.length < 2 ? "Pick two or three players to compare." : undefined}
      />
      {ids.length < MAX_COMPARE && <PlayerPicker exclude={ids} onPick={(id) => setIds(withPlayer(ids, id))} />}
      {ids.length > 0 && (
        <div className={`grid grid-cols-1 gap-8 ${GRID_BY_COUNT[ids.length] ?? ""}`}>
          {ids.map((id) => <Column key={id} gsisId={id} onRemove={() => setIds(withoutPlayer(ids, id))} />)}
        </div>
      )}
    </div>
  );
}
