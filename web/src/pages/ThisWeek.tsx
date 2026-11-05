import { PageHeader } from "@/components/PageHeader";
import { DigestView } from "@/features/digest/DigestView";
import { HomeLeagues } from "@/features/home/HomeLeagues";
import { Answer } from "@/features/thisweek/Answer";
import { ThisWeekBoard } from "@/features/thisweek/ThisWeekBoard";
import { usePageEyebrow } from "@/lib/week";

/** This week: what to do first across both leagues, the week's deadlines and what changed since the last visit; the per-league cards and digest sit under "League details". */
export default function ThisWeek() {
  const eyebrow = usePageEyebrow("This week");
  return (
    <div className="flex flex-col">
      <PageHeader title="What should I do this week?" eyebrow={eyebrow} answer={<Answer />} />
      <ThisWeekBoard />
      <details className="border-t border-line pt-2">
        <summary className="flex min-h-[44px] cursor-pointer items-center text-section font-semibold">League details</summary>
        <div className="flex flex-col gap-8 pt-4">
          <HomeLeagues />
          <DigestView />
        </div>
      </details>
    </div>
  );
}
