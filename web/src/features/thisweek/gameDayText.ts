import { possessive } from "@/lib/text";
import { formatNumber } from "@/viz";

type Numbers = {
  my_team: string;
  opp_team: string;
  my_points: number;
  opp_points: number;
  opp_projected: number;
  my_left: number;
  opp_left: number;
  points_needed: number;
};

const players = (n: number) => `${n} player${n === 1 ? "" : "s"} left`;
/** Both sides have nothing left to score: the matchup is decided. */
export const isDecided = (c: Pick<Numbers, "my_left" | "opp_left">) => c.my_left === 0 && c.opp_left === 0;

/** The "points needed" line, in plain words for finished and already-ahead cases. */
export function neededLine(c: Numbers): string {
  const n = formatNumber;
  if (isDecided(c)) {
    if (c.my_points > c.opp_points) return `Final: won by ${n(c.my_points - c.opp_points)}.`;
    if (c.my_points < c.opp_points) return `Final: lost ${n(c.my_points)} to ${n(c.opp_points)}.`;
    return `Final: tied at ${n(c.my_points)}.`;
  }
  if (c.points_needed <= 0) {
    return `You are already ${n(-c.points_needed)} past ${possessive(c.opp_team)} projected final of ${n(c.opp_projected)}.`;
  }
  if (c.my_left === 0) {
    return `No players left; to reach ${possessive(c.opp_team)} projected final you would need ${n(c.points_needed)} points that can't come.`;
  }
  return `To reach ${possessive(c.opp_team)} projected final you need ${n(c.points_needed)} points from ${players(c.my_left)}.`;
}

export { players };
