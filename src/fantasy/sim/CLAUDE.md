# src/fantasy/sim: simulation logic

Pure logic. Stages and the API read tables and hand the values in. The `simulate` stage is described in `stages/CLAUDE.md`.

- `sim/league_data.py`: `load_league_data(league, data_dir)` builds the `LeagueData` class (defined in `sim/odds.py`) from the tables. `stages/simulate.py` calls it.
- `LeagueData.kd_slot` holds those values, keyed by (kind, roster id, week). `kd_slot_mean` in `sim/odds.py` reads it, falling back to the league mean.
- `_kd_slot_projections` (in `league_data.py`): each team's K and DEF slots use its best rostered unit's projection, with the league mean where a team has none, and the league-wide spread.
- `sim/blend.py`: current week is the equal mean of ours and each `blend_sources` entry the player has. The next three weeks use ours and Sleeper.
- Injury uses the availability model for a flagged player's next game. Season odds also produce `sim_conditional` (what-ifs) and `sim_win_need` (display only: my playoff odds by wins in the next four games, from the same draws).
- Point-valued effects are measured in the reference league (lowest id) and scaled per league (`sim/scoring_scale.py`). Add a new point-valued effect to a `*_POINT_KINDS` set in `sim/league_data.py` (`OUTLOOK_POINT_KINDS`, `ENVIRONMENT_POINT_KINDS`). Otherwise YinzBurgh (0.5 PPR) is overstated.
