import { currentSeason, statIdsFor } from "@/lib/statLink";
import { PlayerSheet } from "./PlayerSheet";

/** `text` is the visible words when they are not the name; the hidden hint then names the player. */
type Props = { gsisId: string | null; name: string; position: string; text?: string };

/** A player's name as a button that opens the stats sheet where there is a game log; plain text otherwise. */
export function PlayerLink({ gsisId, name, position, text }: Props) {
  if (!gsisId || statIdsFor(position) === null) return <>{text ?? name}</>;
  return <PlayerSheet gsisId={gsisId} name={name} position={position} text={text} season={currentSeason()} />;
}
