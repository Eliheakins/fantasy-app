import { Link, useLocation } from "react-router-dom";
import { navSearch } from "@/components/layout/navLinks";
import { statIdsFor } from "@/lib/statLink";

/** `text` is the visible words when they are not the name; the hidden hint then names the player. */
type Props = { gsisId: string | null; name: string; position: string; text?: string };

/** A player's name as a link to their page (keeping league, team and week); plain text where there is no page (no id, K, DEF). */
export function PlayerLink({ gsisId, name, position, text }: Props) {
  const { search, pathname } = useLocation();
  if (!gsisId || statIdsFor(position) === null) return <>{text ?? name}</>;
  return (
    <Link
      to={{ pathname: `/players/${encodeURIComponent(gsisId)}`, search: navSearch("/players/:gsisId", search, pathname) }}
      className="inline-flex min-h-[44px] items-center text-left underline decoration-line underline-offset-4 hover:decoration-ink lg:min-h-0"
    >
      <span>
        {text ?? name}
        {text && " "}
        {text && <span className="sr-only">for {name}</span>}
      </span>
    </Link>
  );
}
