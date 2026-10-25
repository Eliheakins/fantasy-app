import type { ScoreboardRow, ScoreboardSide } from "./logic";

export const side = (o: Partial<ScoreboardSide> = {}): ScoreboardSide => ({
  roster_id: 1, team_name: "Mine", is_me: false, projected: 110, floor: 90, median: 110, ceiling: 130,
  win_prob: 0.6, points: 24.1, share_left: 0.5, ...o,
});
export const row = (a: Partial<ScoreboardSide> = {}, b: Partial<ScoreboardSide> = {}, o: Partial<ScoreboardRow> = {}): ScoreboardRow => ({
  week: 7, matchup_id: 1, status: "Live", a: side(a), b: side({ roster_id: 2, team_name: "Theirs", win_prob: 0.4, ...b }), ...o,
});
