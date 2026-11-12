import type { LastWeekRow, OddsChangeRow } from "@/lib/digestTypes";
import type { Phase } from "@/features/effects/phase";
import type { Todo } from "./todos";

export type SummaryLeague = { name: string; lastWeek: LastWeekRow | null; odds: OddsChangeRow | null; phase: Phase };

const MAX_LINES = 8;
const PERCENT = 100;
const signed = (n: number): string => (n > 0 ? `+${n}` : String(n));

function resultLine(l: SummaryLeague): string {
  const w = l.lastWeek;
  if (w === null) return `${l.name}: no result yet`;
  return `${l.name}: ${w.result} ${w.points.toFixed(1)} to ${w.opp_points.toFixed(1)}${w.opponent ? ` vs ${w.opponent}` : ""} (week ${w.week})`;
}

function oddsLine(l: SummaryLeague): string | null {
  if (l.phase === "out") return `${l.name}: out of the playoffs`;
  const o = l.odds;
  const title = l.phase === "playoffs";
  const [p, d] = title ? [o?.p_title, o?.d_title] : [o?.p_playoffs, o?.d_playoffs];
  if (p == null) return null;
  const change = d == null ? "" : ` (${signed(Math.round(d * PERCENT))} points)`;
  return `${l.name}: ${title ? "title" : "playoff"} odds ${Math.round(p * PERCENT)}%${change}`;
}

function todoLine(t: Todo, i: number): string {
  const { playoffPoints, points, odds } = t.effect;
  const effect = [
    playoffPoints === null ? null : `${signed(Number(playoffPoints.toFixed(1)))} ${odds === "title" ? "title" : "playoff"} pts`,
    points === null ? null : `${signed(Number(points.toFixed(1)))} points`,
  ].filter((x) => x !== null);
  return `${i + 1}. ${t.title} (${t.leagueName})${effect.length ? `: ${effect.join(", ")}` : ""}`;
}

/** Plain-text weekly summary, 5 to 8 lines, built only from fields the page already shows (no ids, links or ranks). */
export function summaryText(leagues: readonly SummaryLeague[], todos: readonly Todo[]): string {
  const head = [...leagues.map(resultLine), ...leagues.map(oddsLine).filter((x) => x !== null)];
  const rest = todos.length === 0 ? ["To do: nothing needed."] : todos.slice(0, Math.max(1, MAX_LINES - head.length)).map(todoLine);
  return [...head, ...rest].slice(0, MAX_LINES).join("\n");
}
