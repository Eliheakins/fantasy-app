# Projection model: research memo (2026-10-25)

Scope: the ten ranked ideas in the task, checked against the repo at `4e6bc72`. Numbers from
`docs/decisions.md` are cited by entry. Literature references are from memory and were not
re-fetched in this session (marked [mem]); data licence claims were fetched on 2026-10-25
(marked [web]).

## What the repo already does

- Learned model: `stages/learn.py`, `HistGradientBoostingRegressor` (squared error, 400
  iterations, lr 0.03, 15 leaves, min leaf 80, l2 5, fixed in advance). One model for all
  positions with position dummies. Walk-forward by season (expanding window). Trains only on
  player-games with a `player_points` row, so it already predicts E[points | played].
  Availability is a separate classifier (`stages/availability.py`). Idea 5 is therefore half
  built already; what is missing is a separate touchdown part, which belongs with idea 4.
- Features: the lagged stats, lines, schedule, role (age, years, draft pick), depth chart, ECR,
  team pace from play by play, PFR and NGS advanced stats. Draft capital is in (`draft_pick`).
  Combine, contracts, FTN charting, red-zone shares and neutral-script pass rate are not
  (grep finds no `ftn`, `yardline_100`, `goal_to_go`, `combine` loader or `contracts`).
- Not in the repo: quantile or conformal models, isotonic or linear recalibration of the
  learned model, stacking or ridge (ridge exists only in `outlook` and `environment`
  effect fits), monotone constraints, per-position models or settings, empirical-Bayes player
  levels.
- Distribution layer: empirical ratio quantiles (actual / projection) by league, position and
  size tier (`stages/distributions.py`); size calibration is estimated but skipped for the
  learned model (decision of 2026-10-23, "Review follow-ups").
- Sleeper blend: a fixed weight of 0.5 (`sim/blend.py`) for the current week and the next three.
- Clean snapshot data: `proj_snapshots` holds week 7 of 2026 only (2,846 rows, 3 pulls
  between 2026-10-24 00:43Z and 2026-10-25 17:11Z). `sleeper_proj_snapshots` holds weeks 7
  to 10 from the same pulls. `player_points` in the working copy has 46 week-7 rows (the
  Thursday game); Sunday's results land on the next `make refresh`.

## Already tested and rejected (do not re-propose)

Per-player volatility; disagreement as a volatility signal; head-to-head history; weather;
participation; slot corners; QB-out effects; position-by-tier bias correction of the baseline
(0.2 to 0.3% RMSE, judged not worth the code, #38); a 75/25 learned/baseline mix for
rest-of-season sums; size calibration on the learned model (made it worse in 7 of 8
league-seasons).

## Ideas: status, expected gain, test design

All model tests use the repo protocol unless stated: walk-forward by season, scored on
2024, 2025 and 2026 weeks 1 to 6, rows with history and a size-calibrated baseline above 3
points (as `learn.compare_to_baseline`), both leagues. Report RMSE, MAE, mean error, by
position; paired per-week t on squared-error differences against the current learned model
(Diebold and Mariano 1995 [mem]), weeks better, and per-season gains. The week-level t
overstates evidence (shared model and season errors), as the M1 entry notes.

| # | Idea | Status | Expected gain | Effort |
|---|---|---|---|---|
| 1 | Sleeper weight by position (#40) | Untestable now: 0 complete clean weeks | unknown; prior 0.5 to 0.85 | low (harness) |
| 2 | Explain the upward bias | Untested on history | 0 to 0.5% RMSE if a level shift is real | low |
| 3 | Quantile GBM or conformal spread | Untested | pinball 0.5 to 2% | medium |
| 4 | Component models scored per league | Untested | 0 to 1% | high |
| 5 | Hurdle | Played-only training and P(play) exist; TD part goes with 4 | small | n/a |
| 6 | Stack GBM, ridge, baseline by position | 75/25 mix tested for sums only | 0.2 to 0.5% | medium |
| 7 | Per-position settings, monotone constraints | Untested | under 0.5% (keep settings) | medium |
| 8 | Empirical-Bayes player level | Untested; rookies get empty features | rookies only, small overall | medium |
| 9 | Usage then efficiency | After 4 | small | high |
| 10 | Red-zone, neutral pass rate, FTN, combine, contracts placebo | Not ingested | 0.1 to 0.5% each, overlapping | medium |

Notes per idea:

1. **Blend weight.** Stack with non-negative least squares on [learned, Sleeper], per position,
   leave-one-week-out on clean pre-kickoff snapshots, shrunk toward 0.5 unless |t| is 2 or
   more (Breiman 1996, non-negative stacking [mem]). The prior from FantasyData (2019 to 2021)
   is a weight near 0.8 on an outside source against our weaker baseline (decisions,
   "Nine tests"). With today's data the test cannot run; the deliverable is the script, run
   at week 11 with weeks 7 to 10. Also score the Sleeper-0-as-missing rule there.
2. **Bias.** The week 7 numbers (+1.22 learned, +0.65 baseline, about 185 games) are one
   week. The test uses the walk-forward history: mean error by season, position, size tier,
   week and played-or-not, for 2021 to 2026. Candidate causes: (a) the scorecard and the
   training both drop games without a stat line, so a "played but recorded nothing" game is
   absent from both (check the share); (b) 2026 scoring below earlier seasons (scale drift);
   (c) the walk-forward squared-error model is unbiased on average in training but not by
   tier (regression to the mean at the top). Ship recalibration (linear or isotonic per
   position, fit walk-forward on earlier seasons) only if it lowers held-out error.
3. **Spread.** HGB with `loss="quantile"` at 0.1, 0.25, 0.5, 0.75, 0.9 (scikit-learn 1.9.1
   installed, supports it), sorted to remove crossing (Chernozhukov, Fernandez-Val and
   Galichon 2010 [mem]); and split-conformal or conformalized quantile regression on
   walk-forward residuals (Lei et al. 2018; Romano, Patterson and Candes 2019 [mem]).
   Compare with the tier marginals on pinball loss and 80% coverage by tier, with the exact
   `backtest` scoring functions. Pinball is a proper score for quantiles (Gneiting and
   Raftery 2007 [mem]). The production sampler uses 99 quantile levels; a shipped model must
   produce those or a shape the sampler can use.
4. **Components.** Separate HGB models for receptions, receiving yards, rushing yards,
   passing yards, touchdowns (rec, rush, pass), interceptions, fumbles; points are each
   league's scoring rules applied to the expected components. Touchdowns as Poisson
   (`loss="poisson"`). Expected points of a linear scoring rule equal the rule applied to
   expected components, so the sum is valid for the mean (not for bonuses; check the leagues
   have none). Compare with the direct model on the same rows.
6. **Stacking.** Out-of-fold predictions from the walk-forward (each season predicted by
   earlier seasons), then non-negative weights per position fit on 2021 to 2023 out-of-fold
   rows, scored 2024 on (Wolpert 1992; Breiman 1996 [mem]). Ridge on the same features as a
   second learner.
7. **Settings.** Nested time split: choose per position on 2021 to 2023 (train on earlier),
   score 2024 on. Monotone constraints (increasing in lagged points, expected points,
   implied total, snap share; decreasing in depth rank). Keep current settings if the gain
   is under 0.5%.
8. **Shrinkage.** Rookies and players with under 4 games: blend the model with a position by
   draft-round prior (Efron and Morris 1975 [mem]); score only on those rows and overall.
10. **Data.** Red-zone and goal-line share of team carries and targets (play by play
   `yardline_100` at most 20 and 5), neutral-script pass rate (win probability 20 to 80%,
   first and second down), lagged with `lag_asof` and a horizon shift. FTN charting: 2022 on,
   CC BY-SA 4.0, attribution "FTN Data via nflverse", charted within 48 hours of the game
   [web: nflreadr `load_ftn_charting` reference]; train window 2022 to 2023 only, so test with
   2024 held out and expect weak power. Combine: "courtesy of PFR", no licence stated [web:
   nflreadr `load_combine` reference]; contracts: OverTheCap, no licence stated [web: nflreadr
   `load_contracts`]; private use only, never committed. Contracts serve as a placebo (no
   expected signal beyond draft pick and age). Every feature is also run with the values
   permuted within season and position as a placebo.

## Leakage checks (all experiments)

- Every lagged join uses `lag_asof` or `latest_asof` with `shift = horizon - 1`; a test pins
  each new join (a value from the target game or later must not appear).
- Walk-forward only: no model, weight, quantile or curve fit uses the season it scores.
- Learned projections for 2019 and 2020 are never used to fit anything
  (`store.projection_table()` drops them).
- Nothing is tuned on 2026; 2026 weeks are reported separately as the cleanest holdout.
- Week 7 snapshots are scored only with the last pull before each team's kickoff.

## Unverified

- The nflverse play-by-play licence was not confirmed (the nflverse-data README fetched has no
  licence section). The data stays under the gitignored `data/` regardless.
- Literature references marked [mem] were not re-fetched.
- The "185 finished player-games" week 7 figure comes from the task; the working copy has 46
  scored week-7 rows, so it was computed on newer live data.
