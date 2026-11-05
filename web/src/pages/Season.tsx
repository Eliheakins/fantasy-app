import { LeagueView } from "@/features/league/LeagueView";
import { OutlookView } from "@/features/outlook/OutlookView";
import { RootForSection } from "@/features/season/RootFor";
import { SeasonHeader } from "@/features/season/SeasonHeader";
import { SeasonOdds } from "@/features/season/SeasonOdds";
import { WhatYouNeed } from "@/features/season/WhatYouNeed";
import { usePageEyebrow } from "@/lib/week";

/** Season: the odds answer, what you need, who to root for, the odds chart, then the outlook tables and league sections. */
export default function Season() {
  const eyebrow = usePageEyebrow("Season", true);
  return (
    <div className="flex flex-col gap-8">
      <div>
        <SeasonHeader eyebrow={eyebrow} />
        <WhatYouNeed />
        <RootForSection />
      </div>
      <SeasonOdds />
      <OutlookView />
      <LeagueView />
    </div>
  );
}
