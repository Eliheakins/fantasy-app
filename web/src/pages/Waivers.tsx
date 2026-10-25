import { PageHeader } from "@/components/PageHeader";
import { WaiversContent } from "@/features/waivers/WaiversView";

export default function Waivers() {
  return (
    <div>
      <PageHeader title="Waivers" />
      <WaiversContent />
    </div>
  );
}
