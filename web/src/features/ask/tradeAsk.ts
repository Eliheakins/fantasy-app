/**
 * Trade questions ("trade A for B", "A for B trade", "trade A and B for C"), read by rules only: the
 * model prompt and catalog do not know about them. The answer is the Trades page's own evaluation.
 */
import { formatValue, points } from "@/features/moves/trade/logic";
import type { TradeRequest, TradeSide } from "@/features/moves/trade/types";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";

import { type PlayerMatch, pickCandidate } from "./resolvePlayers";
import { sideMatch } from "./startSit";

export interface TradeOutcome {
  kind: "trade";
  give: string[];
  get: string[];
}

export type TradeRead =
  | { status: "none" }
  | { status: "message"; text: string }
  | { status: "choose"; sure: PlayerDictionaryRow[]; unsure: PlayerMatch[]; give: PlayerMatch[] }
  | { status: "resolved"; outcome: TradeOutcome; names: Record<string, string>; positions: Record<string, string | null> };

/** The most players per side Ask reads (the Trades page allows more, 2 for 2 is what people type). */
const MAX_PER_SIDE = 2;
const LEAD = /^(?:(?:should|would|could)\s+i\s+)?(?:trade|swap)\s+/i;
const LEADING = new RegExp(`${LEAD.source}(.+?)\\s+for\\s+(.+)$`, "i");
const TRAILING = /^(.+?)\s+for\s+(.+?)\s+trade$/i;
const NAME_LIST = /\s*(?:,|&|\band\b)\s*/i;

const names = (side: string) => side.split(NAME_LIST).map((n) => n.trim());

/** The name phrases on each side of a trade question, or null for any other question. */
export function parseTrade(question: string): { give: string[]; get: string[]; hasVerb: boolean } | null {
  const text = question.trim().replace(/[?!.\s]+$/, "");
  const verb = LEADING.exec(text);
  const match = verb ?? TRAILING.exec(text);
  if (!match) {
    return null;
  }
  const [give, get] = [names(match[1]!), names(match[2]!)];
  const valid = (side: string[]) => side.length <= MAX_PER_SIDE && side.every(Boolean);
  return valid(give) && valid(get) ? { give, get, hasVerb: verb !== null } : null;
}

export function readTrade(question: string, dict: readonly PlayerDictionaryRow[]): TradeRead {
  const parsed = parseTrade(question);
  if (!parsed) {
    return { status: "none" };
  }
  const sides: PlayerMatch[][] = [];
  for (const phrases of [parsed.give, parsed.get]) {
    const matches: PlayerMatch[] = [];
    for (const phrase of phrases) {
      const match = sideMatch(phrase, dict);
      if (match === "extra" || match === "none") {
        return parsed.hasVerb
          ? { status: "message", text: `I couldn't find a player called “${phrase}”. Use a last or full name.` }
          : { status: "none" };
      }
      matches.push(match);
    }
    sides.push(matches);
  }
  const [give, get] = sides as [PlayerMatch[], PlayerMatch[]];
  const sure: PlayerDictionaryRow[] = [];
  const unsure: PlayerMatch[] = [];
  for (const match of [...give, ...get]) {
    const pick = pickCandidate(match, []);
    if (pick) {
      sure.push(pick);
    } else {
      unsure.push(match);
    }
  }
  return unsure.length > 0 ? { status: "choose", sure, unsure, give } : finishTrade(sure, give);
}

/** The outcome once every player is settled (also after the user picks between namesakes). `give` tells the sides apart. */
export function finishTrade(players: readonly PlayerDictionaryRow[], give: readonly PlayerMatch[]): TradeRead {
  const giveIds = new Set(give.flatMap((m) => m.candidates.map((c) => c.gsis_id)));
  const ids = players.map((p) => p.gsis_id);
  if (new Set(ids).size !== ids.length) {
    return { status: "message", text: "A player cannot be on both sides of a trade. Name different players." };
  }
  return {
    status: "resolved",
    outcome: {
      kind: "trade",
      give: ids.filter((id) => giveIds.has(id)),
      get: ids.filter((id) => !giveIds.has(id)),
    },
    names: Object.fromEntries(players.map((p) => [p.gsis_id, p.display_name])),
    positions: Object.fromEntries(players.map((p) => [p.gsis_id, p.position])),
  };
}

export type TradePlan = { kind: "evaluate"; request: TradeRequest } | { kind: "handoff"; text: string };

interface OwnerLike {
  gsis_id: string;
  owner: string;
  roster_id: number;
  is_mine: boolean;
}

/** Owners have no row for kickers and defenses (they are not in the stat data), so they are not free agents. */
const UNSUPPORTED_POSITIONS = new Set(["K", "DEF"]);

/** Who to trade with, from the league's owners; anything unclear is handed to the Trades page, never guessed. */
export function planTrade(
  trade: Pick<TradeOutcome, "give" | "get">,
  names: Readonly<Record<string, string>>,
  owners: readonly OwnerLike[],
  positions: Readonly<Record<string, string | null>>,
): TradePlan {
  const byId = new Map(owners.map((o) => [o.gsis_id, o]));
  const name = (id: string) => names[id] ?? id;
  const handoff = (text: string): TradePlan => ({ kind: "handoff", text });
  const notMine = trade.give.filter((id) => !byId.get(id)?.is_mine);
  if (notMine.length > 0) {
    return handoff(`${notMine.map(name).join(" and ")} ${notMine.length > 1 ? "are" : "is"} not on this team's roster.`);
  }
  const unsupported = [...trade.give, ...trade.get].filter((id) => UNSUPPORTED_POSITIONS.has(positions[id] ?? ""));
  if (unsupported.length > 0) {
    return handoff(`${unsupported.map(name).join(" and ")}: kickers and defenses are not supported in Ask trades.`);
  }
  const unowned = trade.get.filter((id) => !byId.has(id));
  if (unowned.length > 0) {
    return handoff(
      `${unowned.map(name).join(" and ")} ${unowned.length > 1 ? "are" : "is"} a free agent or not on any roster in this league.`,
    );
  }
  const mine = trade.get.filter((id) => byId.get(id)?.is_mine);
  if (mine.length > 0) {
    return handoff(`${mine.map(name).join(" and ")} already ${mine.length > 1 ? "are" : "is"} on this team.`);
  }
  // Teams can share a name, so they are told apart by roster id.
  const rosters = [...new Set(trade.get.map((id) => byId.get(id)!.roster_id))];
  if (rosters.length > 1) {
    return handoff(`${trade.get.map(name).join(" and ")} are on different teams. Pick one trade partner.`);
  }
  return { kind: "evaluate", request: { partner_roster_id: rosters[0]!, give_ids: [...trade.give], get_ids: [...trade.get] } };
}

/** The verb and object of one measure's change, like "lowers" and "your title odds by 0.5 points". */
const clause = (label: string, change: number): [string, string] => {
  const text = formatValue(Math.abs(change), false);
  if (Number(text) === 0) {
    return ["leaves", `your ${label} odds unchanged`];
  }
  return [change > 0 ? "raises" : "lowers", `your ${label} odds by ${text} points`];
};

/** One plain sentence on what the trade does to the viewed team's odds, rounded as the result shows them. */
export function tradeSummary(me: TradeSide): string {
  const [playoffVerb, playoff] = clause("playoff", points(me.playoff_after - me.playoff_before));
  const [titleVerb, title] = clause("title", points(me.title_after - me.title_before));
  // The same verb for both is said once: "lowers A and B", not "lowers A and lowers B".
  return `This trade ${playoffVerb} ${playoff} and ${playoffVerb === titleVerb ? "" : `${titleVerb} `}${title}.`;
}
