import { PageHeader } from "@/components/PageHeader";
import { DigestView } from "@/features/digest/DigestView";
import { NAV_ITEMS } from "@/nav";

const TITLE = NAV_ITEMS.find((n) => n.path === "/digest")?.title ?? "Weekly digest";

export default function Digest() {
  return (
    <section>
      <PageHeader title={TITLE} subtitle="What happened last week and what to do next, read from the last refresh." />
      <DigestView />
    </section>
  );
}
