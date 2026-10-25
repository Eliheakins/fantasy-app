import { PageHeader } from "@/components/PageHeader";
import { OutlookView } from "@/features/outlook/OutlookView";

export default function Outlook() {
  return (
    <section>
      <PageHeader title="Outlook" />
      <OutlookView />
    </section>
  );
}
