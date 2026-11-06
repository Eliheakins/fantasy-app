import { PlayerLink } from "@/components/PlayerLink";
import { EffectText } from "@/features/thisweek/TodoList";
import { MOVE_NOISE_PERCENT, type Move } from "./moves";

function MoveTitle({ move }: { move: Move }) {
  if (move.player === null || move.drop === null) return <>{move.title}</>;
  return (
    <>
      Add <PlayerLink gsisId={move.player.gsisId} name={move.player.name} position={move.player.position} />, drop {move.drop.name}
    </>
  );
}

function MoveNotes({ move }: { move: Move }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 text-caption text-muted">
      {move.detail && <span>{move.detail}</span>}
      {move.trendingAdds != null && <span>Trending: {move.trendingAdds.toLocaleString("en-US")} adds across Sleeper</span>}
    </div>
  );
}

/** Moves in the order given; the first is the best. */
export function MoveList({ moves, empty }: { moves: readonly Move[]; empty: string }) {
  if (moves.length === 0) return <p className="text-body">{empty}</p>;
  return (
    <ol className="divide-y divide-panel-line">
      {moves.map((m, i) => (
        <li key={m.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3 first:pt-0 last:pb-0">
          <span aria-hidden className="w-5 text-caption font-semibold text-muted tabular-nums">{i + 1}</span>
          <div className="min-w-0 flex-1">
            <span className="font-semibold"><MoveTitle move={m} /></span>
            <MoveNotes move={m} />
          </div>
          <EffectText todo={m} playoffNoise={MOVE_NOISE_PERCENT} />
        </li>
      ))}
    </ol>
  );
}
