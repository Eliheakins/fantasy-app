import type { Draft, MarketSummary, TradeRequest, TradeSide } from "./types";

/** The API rejects more ids than this per side. */
export const MAX_TRADE_IDS = 10;
export const EMPTY_DRAFT: Draft = { partner: null, give: [], get: [] };

/** Add the id (unless the side is full) or remove it. Returns a new list. */
export function toggleId(ids: readonly string[], id: string, max = MAX_TRADE_IDS): readonly string[] {
  if (ids.includes(id)) return ids.filter((x) => x !== id);
  return ids.length >= max ? ids : [...ids, id];
}

export function canEvaluate(draft: Draft): draft is Draft & { partner: number } {
  return draft.partner !== null && draft.give.length > 0 && draft.get.length > 0;
}

export function toRequest(draft: Draft): TradeRequest | null {
  if (!canEvaluate(draft)) return null;
  return { partner_roster_id: draft.partner, give_ids: [...draft.give], get_ids: [...draft.get] };
}

/** Same trade regardless of the order the assets were ticked. */
export function tradeKey(draft: Draft): string {
  return JSON.stringify([draft.partner, [...draft.give].sort(), [...draft.get].sort()]);
}

export type Measure = { key: string; label: string; before: number; after: number; percent: boolean };

/** The three before/after measures of one side; probabilities become percentage points. */
export function sideMeasures(side: TradeSide): [Measure, Measure, Measure] {
  return [
    { key: "playoff", label: "Make playoffs", before: side.playoff_before * 100, after: side.playoff_after * 100, percent: true },
    { key: "title", label: "Win the title", before: side.title_before * 100, after: side.title_after * 100, percent: true },
    { key: "wins", label: "Expected wins", before: side.wins_before, after: side.wins_after, percent: false },
  ];
}

export function formatValue(value: number, percent: boolean): string {
  return `${value.toFixed(1)}${percent ? "%" : ""}`;
}

/** "+1.2%" or "-0.4" with an explicit sign, for the text equivalent. */
export function formatSigned(value: number, percent: boolean): string {
  const text = value.toFixed(1);
  const signed = Number(text) === 0 ? "0.0" : value > 0 ? `+${text}` : text;
  return `${signed}${percent ? "%" : ""}`;
}

/** Probability change to points. */
export const points = (fraction: number): number => fraction * 100;

/** "gives 5,000, gets 5,700, you receive 14% more": what the market says, nothing about acceptance. */
export function marketText(m: MarketSummary): string {
  const n = (v: number) => Math.round(v).toLocaleString("en-US");
  return `gives ${n(m.give_value)}, gets ${n(m.get_value)}, ${m.hint}`;
}

/** The date part of the values' fetch time. */
export const marketDate = (m: MarketSummary): string => m.fetched_at.slice(0, 10);
