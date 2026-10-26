import { PageHeader } from "@/components/PageHeader";
import { WaiversContent } from "@/features/waivers/WaiversView";

export default function Waivers() {
  return (
    <section>
      <PageHeader title="Waivers" />
      <WaiversContent />
    </section>
  );
}
