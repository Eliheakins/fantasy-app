# Research scripts

One-off analysis scripts behind the entries in `docs/decisions.md`. They are not maintained code:
ruff skips this folder and no test imports it. They were written ad hoc in a scratch directory and
copied here afterward with their paths pointed at `research/scratch/` (gitignored). They have not
been rerun since the copy, so expect to fix a path or a column name.

Run from the repo root with `make refresh` already done: `uv run python research/<script>.py`.
Each script prints its result; the decisions log has the numbers that were acted on.

## Build the shared panels first (the tests read them)

| Script | Writes | What it builds |
|---|---|---|
| `team_epa.py` | `team_game_epa.parquet` | Team EPA and sack rate per game from play by play |
| `outlook_panel.py` | `outlook_panel.parquet` | Player-game panel: miss against projection, gap since last game, usage |
| `outlook2.py` | `outlook_panel2.parquet` | Adds trends and opponent features to the panel |
| `avail_build.py` | `team_avail.parquet` | Team-level absences (offensive line, defense) per game from snaps and injuries |

## Tests behind a decision

All score a candidate feature out of sample (fit 2019 to 2023, score 2024 onward) against the
baseline. A feature ships only if it improves held-out error.

| Script | Question | Result |
|---|---|---|
| `avail_test.py` | Do offensive line starters out, or safeties, linebackers and linemen out, move player points? | No, except the opposing leading corner (shipped as environment effects) |
| `epa_test.py`, `epa_test2.py` | Do opponent defense efficiency and team offense efficiency predict misses? | Offense sack rate and pass efficiency mean-revert a little (shipped); opponent defense no |
| `ctx_test.py` | Is the Vegas implied-total exponent of 0.5 right? | Yes; refit the calibration per exponent, 0.5 won |
| `qb_test.py` | Does the starting QB being out change teammates' points? | No |
| `replication.py` | Do the shipped environment effects keep their sign in 2019-2023 and 2024 on? | Opposing corner out and pass efficiency do; sack rate does not (switched off) |
| `team_score_backtest.py` | Is the weekly team-score spread calibrated on seasons the fit did not see? | Pooled spread 20% too wide; spread by size tier fixed most of it |
| `data_value.py` | Which free nflverse datasets add held-out accuracy to a learned model? | Depth charts, roster data, PFR and NGS advanced stats, schedule weather and team pace each add 0.01 to 0.025 RMSE; participation adds nothing; all six: 0.059 |
| `fd_panel.py`, `fd_tests.py` | What does an outside weekly projection (FantasyData, open set, 2019-2021) tell us about ours? Nine tests, leave-one-season-out | It beats ours (6.71 vs 6.99); best weight on it 0.8, the same in every segment; the game-script exponent was too high (0.5 to 0.25, shipped) |
| `slot_test.py` | Does a slot corner being out help slot receivers? | Not measurable with free data (no alignment) |
| `h2h_test.py` | Does history against a specific opponent predict points, divisional or not? | No out-of-sample signal |
| `inj_explore.py` | How do injury status, practice report and injury type predict playing? | Became `stages/injuries.py` |
| `weather_check.py` | Do actual temperature and wind add held-out accuracy to the learned model, by position? | No: every variant is within a random-noise placebo (gain 0.04% or less overall, \|t\| below 2) |
| `gbm_test.py` | Does a learned gradient-boosted model beat the rolling baseline on 2024 to 2026? | Yes, about 2% lower RMSE in both leagues (shipped as `proj_learned`) |
| `ecr_value.py` | Do FantasyPros weekly expert rankings improve the learned model? | Shipped as features (`nfl_ecr`, private use) |
| `ros_check.py` | Is the learned model better over the rest of the season (summed forecasts)? | Yes, about 1.6 to 1.9% lower RMSE than the baseline |
| `layers_check.py` | Do the outlook and environment layers help on seasons they never saw? | Outlook layer kept (helps on average); environment layer no held-out gain, switched off |
| `availability_check.py` | Does a chance-of-playing classifier beat the injury-status table? | Yes, Brier 0.0980 against 0.1041 on listed player-weeks (shipped as `stages/availability.py`) |
| `sleeper_proj.py` | How do Sleeper's projections compare with ours? | Not clean: the endpoint re-stamps after games (issue #40 reruns it on clean snapshots) |
| `bias_check.py` | Is the learned projection biased upward, and does recalibration help? | Not on training rows (2026 weeks 1 to 6: -0.3); the scorecard's extra stat-less rows put it at +0.2 to +0.65; recalibration does not help |
| `union_check.py` | Should the learned model also train on stat-less `player_points` rows? | Scorecard rows 1.2% better (t 10); Colgate training rows 0.17% worse; not shipped (open question) |
| `blend_weight.py` | What Sleeper weight do clean pre-kickoff snapshots support (#40)? | Harness only: 0 clean scored games on 2026-10-25; rerun after week 10 |
| `availability_target_check.py` | Should the chance-of-playing classifier predict a stat line rather than any snaps? | Not for Questionable players (t 0.0 to 1.1); across all regulars yes, mostly TE |
| `quantile_check.py` | Do quantile GBM or conformal quantiles beat the tier marginals for the spread? | No: 0.00 to 0.13% pinball against production's tiers, inside refit noise |
| `stack_check.py` | Does a non-negative stack of GBM, ridge and baseline beat the GBM? | No: +0.04 to 0.09% RMSE, t below 0.4 |
| `settings_check.py` | Do per-position models, other GBM settings or monotone constraints help? | No: per-position -0.08 to +0.19% with early stopping matched; best grid point +0.02 to 0.08%; monotone -0.04 to -0.12% |
| `component_check.py` | Do per-stat models (Poisson touchdowns), their average with the direct model, or usage-first beat it? | No: the average's +0.3% does not beat averaging two direct fits (t 1.0 to 1.3) and comes from 2025 |
| `pbp_features_check.py` | Do red-zone and goal-line shares, neutral pass rate, FTN charting, combine or contracts help? | No: all within 0.11% RMSE and within their placebos |
| `td_redundancy_check.py` | Is goal-line share redundant with lagged expected touchdowns? | Correlated (0.85), and both add nothing beyond lagged points |
| `shrink_check.py` | Does shrinking low-game players toward a position-by-round prior help? | k/(k+n) picks k = 0; a variant formed after looking gains 0.05% overall (t 1.9 to 2.0), not shipped |
| `variants_check.py` | Fixed iterations, seed bagging, Poisson loss, per-player residual shrinkage? | Fixed 160 iterations shipped (noise-level, removes row-order dependence); the rest below the ship rules |

`wf_panel.py` is a shared helper for `stack_check.py` and `settings_check.py`. The plan behind the
2026-10-25 tests is in `memo_projection_2026-10-25.md`.

Left out on purpose: seven exploratory scripts that only inspected data shapes (participation
files, snap-count joins, rosters).
