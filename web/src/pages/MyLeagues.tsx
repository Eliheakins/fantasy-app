import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { AddLeague } from "@/features/leagues/AddLeague";
import { MyLeagueList } from "@/features/leagues/MyLeagueList";

/** Where a signed-in person adds their own Sleeper leagues and sees how each is doing. */
export default function MyLeagues() {
  const [username, setUsername] = useState("");
  return (
    <section className="px-[var(--page-pad)] py-6">
      <PageHeader title="My leagues" subtitle="Add your Sleeper leagues to get the same projections and advice." />
      <Section title="Your leagues" caption="You can add up to 2. A new league is read at the next refresh.">
        <MyLeagueList />
      </Section>
      <Section title="Add a league">
        <AddLeague username={username} onUsername={setUsername} />
      </Section>
    </section>
  );
}
