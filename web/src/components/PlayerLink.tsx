import { Link, useLocation } from "react-router-dom";
import { currentSeason, statLink } from "@/lib/statLink";

/** `text` is the visible words when they are not the name; the hidden hint then names the player. */
type Props = { gsisId: string | null; name: string; position: string; text?: string };

/** A player's name, linked to its game log in Explore where one exists; plain text otherwise. */
export function PlayerLink({ gsisId, name, position, text }: Props) {
  const { search } = useLocation();
  const href = statLink({ gsisId, position, season: currentSeason(), search });
  if (href === null) return <>{text ?? name}</>;
  return (
    <Link
      to={href}
      className="inline-flex min-h-[44px] items-center underline decoration-border underline-offset-4 hover:decoration-text lg:min-h-0"
    >
      <span>
        {text ?? name}{" "}
        <span className="sr-only">{text ? `for ${name}, ` : ""}game log</span>
      </span>
    </Link>
  );
}
