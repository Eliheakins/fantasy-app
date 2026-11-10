import { formatPercent } from "@/viz";

/** What drives each of an effect's two numbers, in words, from fields already in the response. Null when there is no number to explain. */
export type EffectWhy = { playoff: string | null; points: string | null };

export const waiverWhy = (get: string, give: string): EffectWhy => ({
  playoff: `Your chance to make the playoffs after adding ${get} and dropping ${give}, minus before, simulated on the same random draws with your lineup re-picked each time. It is net of the drop.`,
  points: `Change in your expected points with ${get} in and ${give} out, net of the drop. Playoff points and fantasy points are never converted into each other.`,
});

export const tradeWhy = (give: string, get: string): EffectWhy => ({
  playoff: `Change in your chance to make the playoffs if you give ${give} and get ${get}, from the stored season simulation.`,
  points: `Change in your expected points from this trade.`,
});

/** A start/sit or injury action: the gain is expected points as the recommendation states it; the share counts wins between the two lineups, not points. */
export const lineupWhy = (share: number | null | undefined): EffectWhy => ({
  playoff: null,
  points:
    share == null
      ? "Expected points gained by making this change, as stated in the recommendation."
      : `Expected points gained by making this change, as stated in the recommendation. Of the held-out simulated games where only one of the two lineups beats your opponent, ${formatPercent(share)} are this lineup's.`,
});
