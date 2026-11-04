import { NLQPanel } from "@/features/nlq/NLQPanel";
import { PageHeader } from "@/shared/components/PageHeader";

export function AskPage() {
  return (
    <div className="mx-auto w-full max-w-3xl flex-1 space-y-4 px-4 pb-12 pt-4 lg:max-w-4xl lg:px-8 lg:pt-6">
      <PageHeader
        eyebrow="Workbench / Ask"
        title="Natural language"
        description="Ask in plain language. Player names are matched in your browser and a local model picks the stats; the numbers are computed in your browser from play-by-play data."
      />
      <NLQPanel />
    </div>
  );
}
