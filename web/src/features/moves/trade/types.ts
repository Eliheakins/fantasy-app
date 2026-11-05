import type { components } from "@/api/schema";

type Schemas = components["schemas"];

export type Partner = Schemas["PartnerRow"];
export type Asset = Schemas["AssetRow"];
export type Strength = Schemas["StrengthRow"];
export type FoundTrade = Schemas["FoundTradeRow"];
export type MarketSummary = Schemas["MarketSummary"];
export type TradeSide = Schemas["TradeSideRow"];
export type TradeEvaluation = Schemas["TradeEvaluation"];
export type TradeRequest = Schemas["TradeRequest"];

/** What the form holds; evaluating needs a partner and at least one asset on each side. */
export type Draft = { partner: number | null; give: readonly string[]; get: readonly string[] };
