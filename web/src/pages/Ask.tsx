import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { HistoryPanel } from "@/features/ask/HistoryPanel";
import { NLQPanel } from "@/features/ask/NLQPanel";
import { ManifestProvider } from "@/features/explore/manifest";

/** Ask in plain language: rules read the question first, a local model the rest, and Explore's engine answers. */
export default function Ask() {
  const [tab, setTab] = useState("ask");
  return (
    <section>
      <PageHeader
        title="Ask"
        eyebrow="Ask · players, stats, start or sit, trades"
        subtitle="Ask in plain language, like Mahomes passing yards and touchdowns in 2023. The answer is a link: reload or share it and nothing is asked again."
      />
      <TooltipProvider>
        <ManifestProvider>
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList aria-label="Ask">
              <TabsTrigger value="ask">Ask</TabsTrigger>
              <TabsTrigger value="history">History</TabsTrigger>
            </TabsList>
            <TabsContent value="ask">
              <NLQPanel />
            </TabsContent>
            <TabsContent value="history">
              <HistoryPanel onReopen={() => setTab("ask")} />
            </TabsContent>
          </Tabs>
        </ManifestProvider>
      </TooltipProvider>
    </section>
  );
}
