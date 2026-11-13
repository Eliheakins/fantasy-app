import { useLocation } from "react-router";
import { PageHeader } from "@/components/PageHeader";
import { FindPlayersCta, PlayersNav } from "@/features/players/PlayersNav";
import { PlayersView } from "@/features/players/PlayersView";
import { usePageEyebrow } from "@/lib/week";

/** Your players: the outlook table, under the Players tabs, with a way into the stat finder. */
export default function Players() {
  const eyebrow = usePageEyebrow("Players");
  const here = useLocation();
  return (
    <div>
      <PlayersNav here={here} />
      <PageHeader title="Your players" eyebrow={eyebrow} />
      <FindPlayersCta here={here} />
      <PlayersView />
    </div>
  );
}
