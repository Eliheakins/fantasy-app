# Research

One-off analysis scripts behind the entries in `docs/decisions.md`, grouped below by topic. They
are not maintained code: ruff skips this folder and no test imports it. Older scripts were written
in a scratch directory and copied here; expect to fix a path or a column name before a rerun.

Run from the repo root with `make refresh` already done: `uv run python research/<script>.py`.
Each script prints its result; the decisions log (entry date in the last column) has the numbers
that were acted on. Caches go to `research/scratch/` (gitignored). Third-party data (prop archives,
outside projections, FantasyPros) stays there and is never committed.

The scripts sit in one folder on purpose: several import a sibling (`wf_panel`, `bias_check`,
`pbp_features_check`, `fd_panel`, `data_value`), which works because Python puts the script's own
folder on the path.

## Notes

| Note | What it is |
|---|---|
| `notes/2026-10-25-projection-memo.md` | Plan for the ten projection ideas: what the repo already did, test design, leakage rules |
| `notes/2026-10-26-research-survey.md` | Survey of literature, GitHub models, outside projection sources, prop methods and simulation practice, with sources |

## How a test is run (since 2026-10-25)

Walk-forward by season (each season scored by models trained on earlier ones), scored on 2024,
2025 and 2026, on the `learn.compare_to_baseline` rows unless a script says otherwise; RMSE with a
paired per-week t; the two leagues share player-games, so they are one test. The ship rule is
written down before the run. Gains under about 0.1% are inside refit noise for anything that is
not deterministic (see the 2026-10-25 entry).

## Shared panels and helpers (build or import first)

| Script | Writes or provides | Used by |
|---|---|---|
| `team_epa.py` | `team_game_epa.parquet`: team EPA and sack rate per game | `epa_test*.py` |
| `outlook_panel.py` | `outlook_panel.parquet`: miss against projection, gap since last game, usage | outlook tests |
| `outlook2.py` | `outlook_panel2.parquet`: adds trends and opponent features | outlook tests |
| `avail_build.py` | `team_avail.parquet`: team absences per game from snaps and injuries | `avail_test.py` |
| `fd_panel.py` | FantasyData 2019 to 2021 panel rescored under each league | `fd_tests.py`, `gbm_test.py` |
| `wf_panel.py` | walk-forward panel and helpers for model variants | `stack_check.py`, `settings_check.py`, `variants_check.py`, `reconcile_check.py`, `kdef_pairs.py` |
| `bias_check.py` | protocol and scorecard row sets (also a test, below) | `union_check.py`, `props_check.py` |
| `pbp_features_check.py` | play-by-play feature builders (also a test, below) | `shrink_check.py`, `td_redundancy_check.py` |

## The learned model itself

| Script | Question | Result | Status | Log |
|---|---|---|---|---|
| `gbm_test.py` | Does a gradient-boosted model beat the rolling baseline? | About 2% lower RMSE in both leagues | Shipped (`proj_learned`) | 10-23 |
| `ros_check.py` | Is it better over the rest of the season (summed forecasts)? | 1.6 to 3.6% lower RMSE than the baseline | Confirmed | 10-23 |
| `ctx_test.py` | Is the Vegas implied-total exponent right? | Flat surface; 0.25 taken later | Shipped | 10-23 |
| `stack_check.py` | Does a non-negative stack of GBM, ridge and baseline beat the GBM? | +0.04 to 0.09%, t below 0.4 | Rejected | 10-25 |
| `settings_check.py` | Per-position models, other settings, monotone constraints? | Per-position -0.08 to +0.19% (early stopping matched); grid +0.02 to 0.08%; monotone -0.04 to -0.12% | Rejected | 10-25 |
| `component_check.py` | Per-stat models (Poisson TDs), their average with the direct model, usage-first? | The average's +0.3% does not beat averaging two direct fits (t 1.0 to 1.3), comes from 2025 | Rejected | 10-25 |
| `shrink_check.py` | Shrink low-game players toward a position-by-round prior? | k picks 0; a post-hoc variant +0.05% (t 1.9 to 2.0) | Rejected | 10-25 |
| `variants_check.py` | Fixed iterations, seed bagging, Poisson loss, per-player residual shrinkage? | Fixed 160 iterations (noise level, deterministic); others below the rules | Fixed iterations shipped | 10-26 |

## What the model predicts: bias, row set, availability

| Script | Question | Result | Status | Log |
|---|---|---|---|---|
| `bias_check.py` | Is the learned projection biased upward; does recalibration help? | Not on training rows (2026 weeks 1 to 6: -0.3); stat-less games put the scorecard at +0.2 to +0.65; recalibration does not help | Explained | 10-25 |
| `hurdle_check.py`, `hurdle_followup_check.py`, `hurdle_played_check.py` | q = P(stat line \| played) times the learned model (first version, review follow-ups, final rerun on played games)? | All played games -3.03% and -2.51% (t 25); protocol rows -0.21% and -0.09% | Built, switched off (open decision) | 10-26 |
| `union_check.py` | Train on stat-less `player_points` rows too? | Scorecard rows 1.2% better (t 10); Colgate training rows 0.17% worse | Rejected (superseded by the hurdle) | 10-25 |
| `inj_explore.py` | How do status, practice and injury type predict playing? | | Became `stages/injuries.py` | 10-23 |
| `availability_check.py` | Does a chance-of-playing classifier beat the injury table? | Brier 0.0980 against 0.1041 on listed player-weeks | Shipped (`stages/availability.py`) | 10-23 |
| `availability_target_check.py` | Should that classifier predict a stat line rather than any snaps? | Not for Questionable players (t 0.0 to 1.1) | Rejected | 10-25 |

## Features from free data

| Script | Question | Result | Status | Log |
|---|---|---|---|---|
| `data_value.py` | Which free nflverse datasets add held-out accuracy? | Depth, rosters, PFR/NGS, schedules, pace 0.01 to 0.025 RMSE each; participation nothing | Shipped (M4) | 10-23 |
| `ecr_value.py` | Do FantasyPros weekly rankings help? | 0.02 RMSE, mostly QB and TE | Shipped (`nfl_ecr`, private use) | 10-23 |
| `pbp_features_check.py` | Red-zone and goal-line shares, neutral pass rate, FTN, combine, contracts? | All within 0.11% and within their placebos | Rejected | 10-25 |
| `td_redundancy_check.py` | Is goal-line share redundant with lagged expected TDs? | Correlated 0.85; both add nothing beyond lagged points | Explained | 10-25 |
| `news_features_check.py` | Teammate vacancy from the final injury report; own status, practice and body part? | Vacancy -0.25 and -0.18% played (t 3.6 and 2.6), -0.46 and -0.40% protocol; own status t below 2 | Vacancy shipped, own rejected | 10-26 |
| `role_features_check.py` | Depth moves, team and coach tenure, weeks since IR or practice squad, pre-kickoff chart? | All under 0.06% overall (t below 2); a post-hoc pair flagged for retest | Rejected | 10-26 |
| `weather_check.py` | Do temperature and wind help the learned model? | Within a random placebo | Rejected | 10-25 |
| `avail_test.py` | Do line, safety or linebacker absences move points? | Only the opposing leading corner | Shipped, later switched off | 10-23 |
| `epa_test.py`, `epa_test2.py` | Do defense and offense efficiency predict misses? | Offense efficiency a little; defense no | Shipped, later switched off | 10-23 |
| `replication.py` | Do the environment effects keep their sign out of sample? | Corner and pass efficiency yes; sack rate no | Partly off | 10-23 |
| `layers_check.py` | Do the outlook and environment layers help held out? | Outlook yes; environment no | Environment off | 10-23 |
| `qb_test.py` | Does a starting QB being out change teammates' points? | No | Rejected | 10-23 |
| `slot_test.py` | Does a slot corner being out help slot receivers? | Not measurable with free data | Rejected | 10-23 |
| `h2h_test.py` | Does history against an opponent predict points? | No | Rejected | 10-23 |

## Decisions (lineups, waivers, injuries, season odds)

| Script | Question | Result | Status | Log |
|---|---|---|---|---|
| `questionable_swap_check.py` | Start a Questionable player by his full projection, or advise a swap at inactives? | Advice +0.18 to 0.27 points a team-week (t about 5); starting by full projection had holes | Swap advice shipped | 10-26 |
| `ir_curve_check.py` | Measured IR return curve against 0 for four games then the chain? | Brier 0.25 to 0.13 and 0.11 | Shipped | 10-26 |
| `season_calibration_check.py` | Are season odds calibrated on built seasons; tau, drift, roster churn? | Calibrated; win totals 10% narrow; no variant clears | Reported | 10-26 |
| `waiver_rule_check.py` | Rest-of-season waiver rule against next-week and form rules (rolling priority)? | +0.94 wins a season over form (t 9.7) | Confirmed; digest ranking changed | 10-26 |
| `blend_regret_check.py` | Does the source blend pick better lineups? | FFToday -0.66 to -0.75 and props -0.37 to -0.47 points a team-week of regret | Confirmed | 10-26 |
| `winprob_check.py` | Do win-probability or ceiling lineups win more games than max points? | 0.03 points of win rate or less, t under 0.7 | Display only | 10-26 |

## Evaluation tools

| Script | Question | Result | Status | Log |
|---|---|---|---|---|
| `regret.py` | Do candidates pick better lineups (start/sit regret, error near the flex cutoff)? | Learned beats baseline by 0.55 to 0.71 points a team-week; component average and reconciliation win against learned but not against a two-seed average | Report only (proposed as a second gate) | 10-26 |
| `news_residual_check.py` | Do day-over-day Sleeper status changes predict the blend's residual? | Harness; archive started 2026-10-26 | Waiting for weeks | 10-26 |

## Spread, correlations and team totals

| Script | Question | Result | Status | Log |
|---|---|---|---|---|
| `team_score_backtest.py` | Is the weekly team-score spread calibrated out of sample? | Pooled spread 20% too wide; size tiers fixed most of it | Shipped (tiers) | 10-23 |
| `quantile_check.py` | Quantile GBM or conformal quantiles instead of tier marginals? | 0.00 to 0.13% pinball against production's tiers | Rejected | 10-25 |
| `reconcile_check.py` | Reconcile player projections with the Vegas team total (scale, MinT)? | Scale +0.08 and +0.11% (t 1.76 and 1.99); MinT worse | Rejected | 10-26 |
| `kdef_pairs.py` | K and DEF correlations; do they improve team-total calibration? | Real (DEF with opposing QB -0.37 to -0.55) but CRPS change 0.02% or less, unstable | Measured, not used | 10-26 |
| `kdef_features_check.py` | Do trailing team, kicker and ranking features beat form plus implied total for K and DEF? | DEF -2.1% and -2.8% RMSE from a joint refit (t -3.7, -4.6); K -1.4% and -1.8% with all features (t -2.1, -2.6); extra DEF groups and K rankings no gain | Shipped (`streaming_model.py`) | 10-27 |
| `opponent_lineup_check.py` | Do managers set lineups worse than their best by projection, and does subtracting it predict their score better? | Mean shortfall 1.75 points (split-half r 0.60); subtracting it raises RMSE 21.42 to 21.99 (t +1.6), team-specific 22.14 (t +1.7) | Rejected | 10-28 |
| `return_hazard_check.py` | Do regulars in their first game back miss the next game more often than others? | No: 13.2% after a return against 16.1% after two straight games (n 1,822 and 12,926; byes in both) | Rejected (no re-injury state needed) | 10-28 |

## Outside sources and blending

| Script | Question | Result | Status | Log |
|---|---|---|---|---|
| `fd_panel.py`, `fd_tests.py` | What does an outside projection (FantasyData 2019 to 2021) tell us? | Beats ours 6.71 to 6.99; best weight on it about 0.8 | Reported; exponent changed | 10-23 |
| `sleeper_proj.py` | How do Sleeper's projections compare? | Not clean: the endpoint re-stamps after games | Superseded by `blend_weight.py` | 10-23 |
| `blend_weight.py` | What weight on Sleeper and other sources do clean pre-kickoff snapshots support (#40)? | Harness; 0 clean scored games on 2026-10-25 | Rerun after week 10 | 10-25 |
| `props_check.py` | Do prop lines add information (free 2024 FanDuel archive)? | Equal blend -1.64 and -1.38% (t 5.2 and 4.3); -1.20 and -0.94% without games where a lead RB or WR sat | Shipped in the source blend (RB, WR) | 10-26 |
| `prop_constants.py` | Yardage and receptions constants (r_m, sigma_m) for prop-implied points | Fit on the free 2024 to 2025 archive; used by `stages/prop_points.py` | Shipped | 10-26 |
| `outside_history.py` | Is FFToday's served history clean, and does an equal mean with ours help? | Looks clean; equal mean -2.0% RMSE on 2025 to 2026 (t -5.5 and -5.7) | Shipped in the source blend | 10-26 |
| `fftoday_bias.py` | Correct FFToday's per-position bias before the mean? | Fit on 2025 (WR +1.16); no worse on 2026 (t -0.4 to -0.6) | Shipped | 10-26 |
| `props_td_check.py` | Is the anytime-TD market better than Sleeper and ours for touchdowns? | Harness; 0 scored games so far | Waiting for weeks | 10-26 |

Left out on purpose: seven exploratory scripts that only inspected data shapes (participation
files, snap-count joins, rosters).
