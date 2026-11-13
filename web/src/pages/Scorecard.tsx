import { ApiBoundary } from "@/components/ApiBoundary";
import { PageHeader } from "@/components/PageHeader";
import { ScorecardView } from "@/features/scorecard/ScorecardView";
import { useLeague, useLeagueApi } from "@/lib/league";

export default function Scorecard() {
  const { league } = useLeague();
  const card = useLeagueApi("/api/leagues/{league}/scorecard");
  return (
    <div key={league}>
      <PageHeader title="Model scorecard" eyebrow="Model · how close the projections were" />
      <ApiBoundary state={card}>{(data) => <ScorecardView data={data} />}</ApiBoundary>
    </div>
  );
}
