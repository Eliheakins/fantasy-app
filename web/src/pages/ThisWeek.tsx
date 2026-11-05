import { PageHeader } from "@/components/PageHeader";
import { DigestView } from "@/features/digest/DigestView";
import { HomeLeagues } from "@/features/home/HomeLeagues";
import { usePageEyebrow } from "@/lib/week";

/** This week: the league cards (the old Home) followed by the weekly digest sections. */
export default function ThisWeek() {
  const eyebrow = usePageEyebrow("This week");
  return (
    <div className="flex flex-col gap-8">
      <PageHeader title="This week" eyebrow={eyebrow} subtitle="What to do now, what happened last week and what to do next, read from the last refresh." />
      <HomeLeagues />
      <DigestView />
    </div>
  );
}
