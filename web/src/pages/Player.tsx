import { useEffect } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiBoundary } from "@/components/ApiBoundary";
import { navSearch } from "@/components/layout/navLinks";
import { PageHeader } from "@/components/PageHeader";
import { PlayerGameLog } from "@/features/players/PlayerGameLog";
import { usePlayer } from "@/features/players/usePlayer";
import { playerDocumentTitle } from "@/hooks/useRouteAnnounce";
import { currentSeason, statIdsFor } from "@/lib/statLink";

function NotFound() {
  const { search, pathname } = useLocation();
  return (
    <section>
      <PageHeader title="Player not found" eyebrow="Players" />
      <p className="measure text-muted">No player in the stat data has that id.</p>
      <Link to={{ pathname: "/players", search: navSearch("/players", search, pathname) }} className="mt-2 inline-flex min-h-[44px] items-center underline">
        Back to Players
      </Link>
    </section>
  );
}

/** The one home for a player: this season's game log and league points. */
export default function Player() {
  const { gsisId = "" } = useParams();
  const state = usePlayer(gsisId);
  const name = state.kind === "ready" && state.data ? state.data.full_name : null;
  useEffect(() => {
    document.title = playerDocumentTitle(name ?? "Player");
  }, [name]);
  return (
    <>
      {state.kind !== "ready" && <PageHeader title="Player" eyebrow="Players" />}
      <ApiBoundary state={state}>
        {(player) =>
          player === null ? (
            <NotFound />
          ) : (
            <div>
              <PageHeader title={player.full_name} eyebrow={["Players", player.position, player.team].filter(Boolean).join(" · ")} />
              {statIdsFor(player.position ?? "") === null ? (
                <p className="text-body text-muted">No stat lines for this position.</p>
              ) : (
                <PlayerGameLog gsisId={gsisId} position={player.position ?? ""} season={currentSeason()} />
              )}
            </div>
          )
        }
      </ApiBoundary>
    </>
  );
}
