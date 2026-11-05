import { PlayerLink } from "@/components/PlayerLink";
import { EffectText } from "@/features/thisweek/TodoList";
import type { Move } from "./moves";

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
      {move.drop && <span>points are net of dropping {move.drop.name}</span>}
      {move.likelyGone && (
        <span className="rounded border border-warning-edge px-1.5 py-0.5 text-ink">
          Likely gone: {move.trendingAdds?.toLocaleString("en-US")} Sleeper adds
        </span>
      )}
    </div>
  );
}

/** Moves in the order given; the first is the best. */
export function MoveList({ moves }: { moves: readonly Move[] }) {
  if (moves.length === 0) return <p className="text-body">No free agent or trade idea raises your odds right now.</p>;
  return (
    <ol className="divide-y divide-panel-line">
      {moves.map((m, i) => (
        <li key={m.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3 first:pt-0 last:pb-0">
          <span aria-hidden className="w-5 text-caption font-semibold text-muted tabular-nums">{i + 1}</span>
          <div className="min-w-0 flex-1">
            <span className="font-semibold"><MoveTitle move={m} /></span>
            <MoveNotes move={m} />
          </div>
          <EffectText todo={m} />
        </li>
      ))}
    </ol>
  );
}
