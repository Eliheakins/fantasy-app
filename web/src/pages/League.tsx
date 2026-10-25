import { PageHeader } from "@/components/PageHeader";
import { LeagueView } from "@/features/league/LeagueView";

export default function League() {
  return (
    <section>
      <PageHeader title="League" />
      <LeagueView />
    </section>
  );
}
