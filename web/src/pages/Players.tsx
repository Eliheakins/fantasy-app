import { PageHeader } from "@/components/PageHeader";
import { PlayersView } from "@/features/players/PlayersView";

export default function Players() {
  return (
    <section>
      <PageHeader title="Player outlook" />
      <PlayersView />
    </section>
  );
}
