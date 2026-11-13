import { Link, useLocation, useParams } from "react-router";
import { ApiBoundary } from "@/components/ApiBoundary";
import { navSearch } from "@/components/layout/navLinks";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { PlayerGameLog } from "@/features/players/PlayerGameLog";
import { PlayerSections } from "@/features/players/PlayerSections";
import { answerSentence, compareHref } from "@/features/players/profile";
import { usePlayer } from "@/features/players/usePlayer";
import { useProfile } from "@/features/players/useProfile";
import { usePageName } from "@/hooks/useRouteAnnounce";
import { currentSeason, statIdsFor } from "@/lib/statLink";
import { linkButtonClass } from "@/components/ui/styles";
import { cn } from "@/lib/utils";

function NotFound() {
  const { search, pathname } = useLocation();
  return (
    <section>
      <PageHeader title="Player not found" eyebrow="Players" />
      <p className="measure text-muted">No player in the stat data has that id.</p>
      <Link to={{ pathname: "/players", search: navSearch("/players", search, pathname) }} className={cn("mt-2", linkButtonClass)}>
        Back to Players
      </Link>
    </section>
  );
}

function CompareLink({ gsisId }: { gsisId: string }) {
  const { search } = useLocation();
  return (
    <Link to={compareHref([gsisId], search)} className={linkButtonClass}>
      Compare with…
    </Link>
  );
}

/** The one home for a player: next game range, rest of season value, role, injury, market, owner, then this season's game log. */
export default function Player() {
  const { gsisId = "" } = useParams();
  const here = useLocation();
  const state = usePlayer(gsisId);
  const profile = useProfile(gsisId);
  const answer = profile.kind === "ready" ? answerSentence(profile.data) : null;
  usePageName(state.kind === "ready" && state.data ? state.data.full_name : null);
  return (
    <>
      {state.kind !== "ready" && <PageHeader title="Player" eyebrow="Players" />}
      <ApiBoundary state={state}>
        {(player) =>
          player === null ? (
            <NotFound />
          ) : (
            <div className="space-y-6">
              <PageHeader
                title={player.full_name}
                eyebrow={["Players", player.position, player.team].filter(Boolean).join(" · ")}
                answer={answer}
                actions={<CompareLink gsisId={gsisId} />}
              />
              <PlayerSections gsisId={gsisId} showResult={answer === null} here={here} />
              <Section title="This season">
                {statIdsFor(player.position ?? "") === null ? (
                  <p className="text-body text-muted">No stat lines for this position.</p>
                ) : (
                  <PlayerGameLog gsisId={gsisId} position={player.position ?? ""} season={currentSeason()} here={here} />
                )}
              </Section>
            </div>
          )
        }
      </ApiBoundary>
    </>
  );
}
