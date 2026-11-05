import { Button } from "@/components/ui/button";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";

import type { PlayerMatch } from "./resolvePlayers";

const CHOICE_LIMIT = 8;

type PlayerChipsProps = {
  players: PlayerDictionaryRow[];
};

type PlayerChoicesProps = {
  choices: PlayerMatch[];
  onChoose: (player: PlayerDictionaryRow) => void;
};

function describe(player: PlayerDictionaryRow): string {
  return `${player.display_name} · ${player.position ?? "?"} · ${player.team ?? "FA"}`;
}

export function PlayerChips({ players }: PlayerChipsProps) {
  if (players.length === 0) {
    return null;
  }
  return (
    <div>
      <p className="mb-1 text-caption font-medium uppercase tracking-wide text-muted">Matched players</p>
      <ul className="flex flex-wrap gap-2">
        {players.map((p) => (
          <li key={p.gsis_id} className="rounded-md border border-line px-2 py-1.5 text-caption text-ink">
            {describe(p)}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Namesakes the stats could not tell apart: one row of buttons per ambiguous name. */
export function PlayerChoices({ choices, onChoose }: PlayerChoicesProps) {
  if (choices.length === 0) {
    return null;
  }
  return (
    <div className="space-y-3">
      {choices.map((match) => (
        <div key={`${match.start}-${match.phrase}`}>
          <p className="mb-1 text-caption font-medium text-muted">
            Which “{match.phrase}”?
            {match.candidates.length > CHOICE_LIMIT ? ` Showing ${CHOICE_LIMIT}; use a full name to narrow.` : ""}
          </p>
          <ul className="flex flex-wrap gap-2">
            {match.candidates.slice(0, CHOICE_LIMIT).map((p) => (
              <li key={p.gsis_id}>
                <Button type="button" variant="outline" size="sm" onClick={() => onChoose(p)}>
                  {describe(p)}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
