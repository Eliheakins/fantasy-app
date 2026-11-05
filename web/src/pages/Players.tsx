import { Link, useLocation } from "react-router-dom";
import { navSearch } from "@/components/layout/navLinks";
import { PageHeader } from "@/components/PageHeader";
import { PlayersView } from "@/features/players/PlayersView";
import { usePageEyebrow } from "@/lib/week";

export default function Players() {
  const { search, pathname } = useLocation();
  const eyebrow = usePageEyebrow("Players");
  return (
    <div>
      <PageHeader
        title="Players"
        eyebrow={eyebrow}
        actions={
          <Link to={{ pathname: "/players/find", search: navSearch("/players/find", search, pathname) }} className="inline-flex min-h-[44px] items-center underline">
            Find players
          </Link>
        }
      />
      <PlayersView />
    </div>
  );
}
