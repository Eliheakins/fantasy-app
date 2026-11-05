import { currentSeason, statLink } from "@/lib/statLink";

/** `text` is the visible words when they are not the name; the hidden hint then names the player. */
type Props = { gsisId: string | null; name: string; position: string; text?: string };

/** A player's name, linked to the stat app's game log where one exists; plain text otherwise. */
export function PlayerLink({ gsisId, name, position, text }: Props) {
  const href = statLink({ gsisId, position, season: currentSeason() });
  if (href === null) return <>{text ?? name}</>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex min-h-[44px] items-center underline decoration-border underline-offset-4 hover:decoration-text lg:min-h-0"
    >
      <span>
        {text ?? name}{" "}
        <span className="sr-only">{text ? `for ${name}, ` : ""}game log, opens in a new tab</span>
      </span>
    </a>
  );
}
