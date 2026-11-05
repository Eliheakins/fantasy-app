import { formatNumber, formatPercent } from "@/viz";
import type { WinProbability } from "./logic";

type Option = WinProbability["options"][number];

/** The win chance on the page: a share of the held-out simulated draws, with both medians so the number can be checked against the ranges. */
export const winChanceWhy = (option: Option | undefined): string =>
  `Share of simulated weeks, on the held-out half of the draws, in which your total beats the opponent's.${
    option ? ` Your median is ${formatNumber(option.median, 0)}, theirs ${formatNumber(option.opp_median, 0)}.` : ""
  }`;

export const SLEEPER_WIN_WHY =
  "Your chance to win with the lineup shown minus your chance with what is set in Sleeper now, from the same paired simulated draws. Percentage points.";
export const SLEEPER_POINTS_WHY =
  "Expected points of the lineup shown minus those of what is set in Sleeper now, skill slots only (no kicker or defense).";

/** A close call's share (the starter's) against the eligible bench player with the highest expected points. */
export const slotShareWhy = (share: number): string =>
  `In ${formatPercent(share)} of paired simulated draws (the same draw scores both players; held-out half; a tie counts half) the starter scores more than the eligible bench player with the highest expected points. Clear is 70% or more, lean 55 to 70%, toss-up under 55%, either way round.`;
