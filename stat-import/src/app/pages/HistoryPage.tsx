import { HistoryPanel } from "@/features/nlq/HistoryPanel";
import { PageHeader } from "@/shared/components/PageHeader";

export function HistoryPage() {
  return (
    <div className="mx-auto w-full max-w-3xl flex-1 space-y-4 px-4 pb-12 pt-4 lg:max-w-4xl lg:px-8 lg:pt-6">
      <PageHeader
        eyebrow="Workbench / History"
        title="Ask history"
        description="What you asked, how it was read, and what you changed. It stays in this browser."
      />
      <HistoryPanel />
    </div>
  );
}
