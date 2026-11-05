import { Section } from "@/components/Section";
import { PageHeader } from "@/components/PageHeader";
import { LeagueView } from "@/features/league/LeagueView";
import { OutlookView } from "@/features/outlook/OutlookView";
import { usePageEyebrow } from "@/lib/week";
import Scoreboard from "@/pages/Scoreboard";

/** Season: the outlook, then the week's scores, then the league sections. */
export default function Season() {
  const eyebrow = usePageEyebrow("Season", true);
  return (
    <div className="flex flex-col gap-8">
      <PageHeader title="Season" eyebrow={eyebrow} />
      <OutlookView />
      <Section title="Scores" caption="This week's matchups, from the week picker in the top bar.">
        <Scoreboard />
      </Section>
      <LeagueView />
    </div>
  );
}
