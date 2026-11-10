import { People } from "@/features/admin/People";
import { RefreshPanel } from "@/features/admin/RefreshPanel";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";

/** For the admin only (the server refuses everyone else): who can sign in, and the data refresh. */
export default function Admin() {
  return (
    <section className="px-[var(--page-pad)] py-6">
      <PageHeader title="Admin" subtitle="People who can sign in, and the data refresh." />
      <Section title="People" caption="Send each person their link yourself. Nothing is emailed.">
        <People />
      </Section>
      <Section title="Refresh">
        <RefreshPanel />
      </Section>
    </section>
  );
}
