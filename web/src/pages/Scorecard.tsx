import { ApiBoundary } from "@/components/ApiBoundary";
import { PageHeader } from "@/components/PageHeader";
import { ScorecardView } from "@/features/scorecard/ScorecardView";
import type { ScorecardData } from "@/features/scorecard/logic";
import { useLeague, useLeagueApi } from "@/lib/league";

export default function Scorecard() {
  const { league } = useLeague();
  const card = useLeagueApi<ScorecardData>("scorecard");
  return (
    <div key={league}>
      <PageHeader title="Model scorecard" />
      <ApiBoundary state={card}>{(data) => <ScorecardView data={data} />}</ApiBoundary>
    </div>
  );
}
