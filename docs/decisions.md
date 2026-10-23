# Decisions log

Newest at the bottom. Record every decision with its date and reason.

## 2026-10-22

- **Purpose:** personal fantasy football app for one user. Copy what the best public tools do, and use advanced math wherever it is feasible to run.
- **Platform:** Sleeper. Rosters and leagues are read through Sleeper's public read-only API.
- **Sport:** NFL only.
- **Format:** redraft, 2 leagues. Dynasty comes later as an epic (see backlog.md).
- **Waivers:** standard waiver priority first. FAAB comes later as an expansion (see backlog.md).
- **Delivery:** runs locally on the laptop, not a web app. Reason: single user, no hosting cost, no auth. A web front end can be added later if wanted.
- **Cost ceiling:** pay for some compute, not a lot. Heavy training is offline and occasional. Inference is precomputed weekly and cached, so it costs close to nothing.
- **Model policy:** ship an own-built projection model only if it beats the in-house baseline in walk-forward backtests (pinball loss, CRPS) and is calibrated. Changed 2026-10-23: the original bar was "consensus blend", but nflverse's ranking data has ranks only, no stat projections.
- **Math over parameters:** player data is small (tens of thousands of player-seasons), so gradient boosting and Bayesian models are preferred over large neural nets. Big compute goes to simulation and ensembling.
- **Note-taking:** record everything important from the conversation in this docs folder.

## Git and accounts (2026-10-22)

- `~/aai/` is work: `EliArsenal`, `eli.heakins@arsenalai.com`, SSH key `~/.ssh/id_ed25519`, host alias `github.com-work`.
- Everywhere else is personal: `Eliheakins`, `123508908+Eliheakins@users.noreply.github.com`, SSH key `~/.ssh/id_ed25519_personal`.
- Config lives in `~/.gitconfig` (default personal, `includeIf` for `~/aai/`), `~/.gitconfig-work` (work identity and URL rewrite), and `~/.ssh/config`.
- Personal repos live under `~/personal/`. `valleyTeacherCoverageApp` was moved there from `~/aai/`, and its remote now uses SSH. The personal key was tested and authenticates as Eliheakins.

## Sleeper account and leagues (2026-10-22)

- Sleeper username `Eliheakins`, user_id `1385113153716641792`.
- The API shows 3 in-season 2026 NFL leagues, not 2. Which are in scope is an open question.

| League | Teams | Format | Scoring | Roster extras | Waivers |
|---|---|---|---|---|---|
| Colgate Fantasy Football (`1394105943137992704`) | 10 | Redraft | 1.0 PPR, -1 INT | Superflex, K, DEF | Priority |
| YinzBurgh (`1385108353306361856`) | 10 | Redraft | 0.5 PPR, -2 INT | K, DEF | Priority |
| Get to da CHOPPA (`1396290986568609792`) | 16 | `type` 3, probably a Chopped/guillotine league (not verified) | 1.0 PPR, -1 INT | No K or DEF, 2 flex | FAAB, 1000 budget |

- Trade deadline is week 11 in all three leagues. Playoffs start week 15 in the two redraft leagues.
- Scoring differs per league (PPR level, INT penalty, superflex), so scoring must be computed per league from each league's settings.
- Both redraft leagues start a K and a DEF, so the app needs at least a simple K and DEF approach.
- Recalled, not verified: Sleeper's public API is read-only, so the app can recommend lineups but cannot set them.

## Scope answers (2026-10-22)

- **Leagues in scope:** Colgate and YinzBurgh. CHOPPA is out of the first build and goes to the backlog as its own expansion.
- **K and DEF:** simple streaming rules (opponent, Vegas totals, weather, dome). No full models.
- **Approach:** lean MVP first, then expand piece by piece. Spend the time where it matters most. Less important parts, UI especially, start rough and get cleaned up later. Design the MVP with clear expansion points.
- **Tracking:** GitHub Issues and a GitHub Project under the personal `Eliheakins` account.
- **Budget:** $0 for now. Free data only. Compute is local on an M5 Pro, and long processing times are acceptable.

## MVP, process, repo (2026-10-22)

- **MVP includes trades.** Scope: start/sit, waivers, and the trade analyzer for Colgate and YinzBurgh. Reason: the week 11 trade deadline. The user also said I underestimate how fast things get built, so size the MVP ambitiously, not cautiously.
- **Process:** no fixed sprints. Kanban on a GitHub Project: pull the next story when the last is done.
- **Capacity:** the user has a Claude Max subscription and can spend about 20% of it on this. Keep stories small so usage can be tracked, and avoid wasteful rework.
- **Language:** Python core (Polars, DuckDB, NumPy, SciPy; LightGBM and NumPyro or PyMC only for the post-MVP model; no optimization solver in the MVP, see refinement pass 2 below). Confirmed 2026-10-22. Stages exchange parquet files so a stage can be swapped to another language later. R is the fallback only if `nflreadpy` lacks the ffopportunity expected-points data (not verified).
- **Data policy:** free sources that allow programmatic use only (Sleeper, nflverse, DynastyProcess, FantasyCalc). No scraping of sites whose terms forbid it (KeepTradeCut, FantasyPros pages). Confirmed.
- **UI:** a dashboard, not a terminal report. Runs locally. Rough at first, experiment with the layout, refine later. Replaces the earlier "command prints a report" idea.
- **Prop lines:** sportsbook bets on individual player stats, usable as market-made projections. At $0 the free odds tier is small and history costs money, so backtests can't include them. Decision pending: leave them out of the MVP and start free weekly snapshots after E2 (recommended), or pay for a month.
- **Prop line cost (The Odds API, checked 2026-10-22):** free 500 credits per month with no historical data, $30 for 20K, $59 for 100K. A call costs 1 credit per market per region, one call per game. Rough need: about 8 markets x 1 region x about 16 games = about 128 credits per weekly snapshot. Historical per-call cost and how far back props history goes were not confirmed in the docs read.
- **Prop credit needs (from docs, 2026-10-22):** events list is free. Live event odds cost unique markets x regions per game. Historical event odds cost 10 x markets x regions per game snapshot, plus 1 per historical events lookup. Up to 10 bookmakers count as 1 region. Useful markets: pass yds, pass TDs, rush yds, receptions, reception yds, anytime TD (core 6), plus pass INTs, plus kicker field goals and kicking points. Team totals and spreads for all games cost 1 credit per market in a single call.
  - Lean (free tier): core 6 markets, 1 snapshot per week, about 400 to 480 credits per month.
  - Recommended: 7 core + 2 kicker markets, plus spreads and totals, 2 snapshots per week (midweek for waivers and trades, game-day morning for lineups), about 1,260 credits per month. Fits the $30 plan 15 times over.
  - Historical backfill: about 300 games per season. At 7 markets one snapshot per game is about 21,000 credits per season. Three seasons is about 63,000 credits, one month of the $59 plan. How far back props history goes is not verified.
- **Props decision (2026-10-22):** use the free tier, lean plan (core 6 markets, 1 snapshot per week), starting after E2. Props stay out of MVP projections. No paid backfill for now.
- **UI stack (proposed, not yet confirmed):** Streamlit first for fast iteration, with a thin data layer so a React front end (Tremor, shadcn) can replace it later.
- **Plan artifact:** `docs/one-pager.md` holds the current epics and build order.

## Spec review results (2026-10-23)

Four agents wrote specs in `docs/spec/` (architecture, modeling, dashboard, data-sources). Merged backlog: `docs/backlog.md`.

- **Baseline:** in-house rolling expected-points model. `load_ff_rankings` is FantasyPros expert ranks only, no stat projections. Model bar is "beat the baseline and be calibrated".
- **ECR:** FantasyPros redistribution terms through nflverse not checked. Nothing depends on it. Weekly archiving of it is on hold until the terms are read.
- **Verified by real calls (week 6 data):** Sleeper ID crosswalk resolves 16 of 17 on each roster (DEF by team code) and 90.9% of active fantasy players. Per-league scoring from nflverse matches Sleeper exactly for 161 of 169 offense and K starters, all 17 of the user's, and 17 of 19 DEF.
- **Data limits:** Vegas lines only through week 8. Weather null from week 5. nflverse stats lag by the last finished week. No past seasons in the user's leagues, so backtests use nflverse history with synthetic 1.0 and 0.5 PPR settings. Team codes differ (`LA` vs `LAR`). Empty Sleeper slots are `"0"`.
- **Storage:** parquet only, DuckDB as in-memory views.
- **UI:** one data module `data_api.py`. No fake-data layer, no dark toggle, no live recompute, no "Both" outside Home.
- **Correlation:** pair-table Gaussian copula with the measured values (QB with WR1 0.35, WR2 0.34, TE1 0.30, RB1 0.08, WR with WR 0.02). A one-factor model was tried and rejected in refinement pass 1 because it forces WR with WR to at least 0.12.
- **Post-MVP:** partner finder, Players search, lineup what-if, own model (E6), Bayesian models.
- **Sequencing:** the trade tool has a week 11 deadline and is worthless after it, while start/sit and waivers last through the playoffs. A fast path to the trade evaluator is in backlog.md.
- **Open:** DEF 2 of 19 mismatch untraced, DEF points-allowed definition (nflverse includes return TDs, Sleeper does not), Sleeper future-week matchups untested (spike moved to E1-1).

## Refinement passes (2026-10-23)

Four passes after the first merge. Backlog is now `docs/backlog.md` v3 (36 stories, 17 on the trade fast path).

1. **Disagreements.** One-factor correlation rejected (forces WR with WR to at least 0.12 against a measured 0.02); pair-table copula kept, shipped as constants. HiGHS dropped: greedy slot fill is optimal for nested eligibility and is checked against brute force. Data layer is one module, `data_api.py`. Simulation counts do not conflict: 20,000 sims is milliseconds at team level, and the architect's 5,000 applies only to the post-MVP partner finder.
2. **Math coherence.** Added persistent per-player error `tau` (weeks were treated as independent, which overstates title odds). Single-matchup win probability is analytic under the Normal team-score model. Opponent's current-week lineup comes from Sleeper's set starters.
3. **Sequencing.** Fast path was wrong: it omitted the shell (E1-3), the minimal backtest (E3-5) and the auto-lineup (E4-1), and wrongly included the player-level sampler (E4-2). Corrected. Cut order written down.
4. **Independent review.** A fresh agent found: confidence tags must come from paired-simulation share including `tau`, not Monte Carlo error; `tau` estimation was circular and ignored weekly noise; rest-of-season projections had no validation; calibration checks could not detect persistent error; unmatched free agents need a fallback; story IDs conflicted across docs; partial-week handling was missing; a market-value field survived in the trade views. All applied except per-player-week availability draws (post-MVP) and dropping the copula (kept as constants).

**Confidence tag definition:** `clear` when the change helps in 70% or more of paired simulations, `lean` at 55 to 70%, `toss-up` below 55%. The simulations include the persistent per-player errors.

## Tooling (2026-10-23)

Set up as part of E0-1, not yet committed. Everything runs from a normal launch: `uv` (already installed) provisions Python 3.12.

- **Runtime:** polars, duckdb, nflreadpy, numpy, scipy, httpx, streamlit.
- **Dev:** ruff (lint and format, line length 100, rules E F I B UP), mypy (lenient, `src` only), pytest.
- **Commands:** `make setup` (sync and enable the git hook), `make check` (ruff, mypy, format check, pytest), `make fmt`.
- **Git hook:** `.githooks/pre-commit` runs the fast ruff checks only. `make setup` points `core.hooksPath` at it.
- **Config:** `config.toml` (season, user id, league ids, sim count) loaded by `fantasy.config.load_config`, with a test.
- **Claude Code:** `CLAUDE.md` with commands and conventions, and a narrow command allowlist in `.claude/settings.json`.
- **Left out on purpose:** CI, pre-commit framework, bandit, coverage thresholds (lean MVP). Add bandit if the odds API key handling grows.

## E1-1 spike results (2026-10-23, from live Sleeper calls)

- **Future matchups are returned.** `GET /league/{id}/matchups/{week}` gives pairings (5 matchup ids for 10 rosters) for weeks 8 to 17 in both leagues, with no points yet. Weeks 15 to 17 also return 5 ids, but those are probably placeholders until the bracket is seeded (not verified), so treat playoff weeks as bracket-determined and use weeks 1 to 14 pairings for the regular season.
- **Playoff settings (both leagues):** `playoff_week_start` 15, `playoff_teams` 6, `playoff_type` 0, `playoff_round_type` 0, `playoff_seed_type` 0. There is no separate tiebreaker field. The meaning of the 0 codes (single elimination, one week per round, default seeding by record then points for) is the assumed Sleeper default and is not verified.
- **Current week:** both leagues report week 7.

## E1 and E2-1 results (2026-10-23)

- **Crosswalk (live run):** 702 of 760 active non-DEF players map to an nflverse ID (58 do not). Every player on both of the user's rosters resolves. Team codes differ across sources (`LAR` vs `LA`, and nflverse's ID table has `GBP`, `KCC`, `LVR`, `NEP`, `NOS`, `SFO`, `TBB`, `JAC`), handled by one map in `crosswalk.py`. Only the Sleeper file's own `gsis_id` is mostly empty (1,322 of 4,266 players).
- **Rule:** players on the user's own rosters that fail to map stop the run. Unmapped players elsewhere stay in `id_map` with `match_method` `none` and show as "no history".
- **ingest_nfl:** six tables for 2018 to 2026 (player stats, team stats, snaps, injuries, schedules, ff_opportunity), 12-hour TTL. Latest week with stats is 6. Spread and total lines exist for week 8 (14 of 14 games) and none for week 12. 81% of 2026 snap rows get a gsis ID through the PFR ID.
- **Depth charts skipped:** nothing in E3 to E5 uses them (the 2026 table alone is 685k rows).
- **Process:** each story is committed and pushed to `main` on its own; the user approved direct pushes for this repo. Issues close through `Closes #n` in the commit message.

## E3-1 scoring result (2026-10-23)

Per-league scoring from nflverse stats matches Sleeper's reported player points **exactly for every non-DEF player in weeks 1 to 6 in both leagues** (about 1,800 player-weeks including benches and kickers), checked with `python -m fantasy.stages.validate_scoring <week>`. One gap was found and fixed by that check: Sleeper counts blocked field goals as misses (`fgmiss` = nflverse `fg_missed` + `fg_blocked`). Defenses are not scored yet (E3-7). `check_keys` raises on any scoring key with points that has no mapping; defense keys (`pts_allow_*`, `yds_allow_*`, `sack`, `int`, and so on) are allowed through for E3-7. Note YinzBurgh scores yards allowed tiers for DEF, which the earlier spec did not mention.

## E3-3 baseline projection (2026-10-23)

- **Method:** per player and target game, using only earlier games: `form = 0.5 * shrunk(expected points) + 0.5 * shrunk(actual points)`, each an exponentially weighted average (half-life 4 games) shrunk toward the position's prior-season mean with K = 3 games, times `(team implied total / season average) ** 0.5` (1.0 when no line exists). Expected points are nflverse's opportunity model scored under each league's rules; they track actual points closely (mean RB 7.9 vs 7.8, WR 6.75 vs 6.76, per-game correlation about 0.8).
- **Honest result:** a trailing average of actual points is hard to beat. On the 2024 to 2025 holdout (n about 20,000 player-games per league scoring) the baseline has RMSE 6.267 vs 6.313 (0.7% better) and MAE 4.742 vs 4.705 (0.8% worse, expected for a mean forecast of right-skewed points). Expected points alone were slightly worse than the trailing average; the blend and the context multiplier each helped a little. Typical miss is about 6 points, so single-game projections are weak. The edge in this app has to come from the distributions, lineups, waivers and trades built on top, not from a better mean.
- **Constants tuned lightly** on 2019 to 2023 and checked on 2024 to 2025. E3-5 formalizes the backtest (pinball loss, +1 and +5 weeks ahead).
- **Coverage:** every QB, RB, WR and TE on both of the user's rosters has a projection for every remaining game; bye weeks have no row (Buffalo and the Chargers are on bye in week 7). Kickers and defenses are E3-7. Projections for weeks beyond the next one use a neutral context because spread and total lines only exist for the next week or two.
- **Tables:** `player_form` (per player-game), `proj_baseline` (walk-forward history from 2019 plus future games). Projections are recomputable, so no archive yet.

## E3-4 distributions (2026-10-23)

- **Marginals:** a Gamma with mean = projection and a per-position coefficient of variation from walk-forward residuals (2019 to 2025): QB about 0.48 to 0.50, RB 0.67 to 0.70, WR 0.70 to 0.75, TE 0.75 to 0.81 (the lower values are the 1.0 PPR league). Estimated as sqrt(sum of squared residuals / sum of squared projections).
- **Correlations measured** (Spearman of walk-forward residuals, converted with rho = 2 sin(pi * rho_s / 6), about 4,000 team-weeks per pair, 1.0 PPR league): same team QB1 with WR1 0.35, WR2 0.31, TE1 0.27, RB1 0.08, RB2 0.03; WR with WR and WR with TE about 0 (0.00 to 0.03). Opposing teams in the same game: QB1 with QB1 0.21, QB1 with opposing WR1 0.10, WR2 0.09, TE1 0.07, RB1 0.04. These replace the modeler's provisional values (which had opposing QB-QB at 0.10). K and DEF correlations are not measured.
- **Tables:** `marginals`, `correlation_pairs` (derived). The pair table is data now, so E4-2 reads it instead of constants. Bootstrap intervals are not computed (post-MVP).

## E3-5 backtest and a correction to E3-4 (2026-10-23)

- **Correction to E3-4:** the Gamma marginal (constant coefficient of variation) was replaced. Its 80% interval covered only 66% to 74% of real outcomes, because real player games have more near-zero outcomes than a Gamma allows. `marginals` now holds the empirical quantiles (1% to 99%) of actual / projected points per league and position, so a player-game's outcome distribution is `projection * ratio quantile`. The correlation table is unchanged.
- **Backtest (`python -m fantasy.stages.backtest`):** distributions fitted on 2019 to 2023, scored out of sample on 2024 to 2025 (about 25,000 player-games per horizon). The baseline beats a trailing average of actual points in all 8 league-position cells at both horizons: pooled pinball loss 1.332 vs 1.364 at +1 week (2.4% lower) and 1.371 vs 1.442 at +5 weeks (4.9% lower); RMSE 6.14 vs 6.18 and 6.33 vs 6.41. The 80% interval covers 82% of outcomes for both. The +5 week forecast uses only data from at least 5 weeks earlier and a neutral context.
- **Caveats:** the ratio quantiles are fitted per league and position on the same weeks-to-seasons window as the projection constants (half-life, shrinkage, blend weight), which were tuned lightly on 2019 to 2023, so the 2024 to 2025 numbers are a fair holdout but not a long one. The edge is real but modest: single-game outcomes remain very noisy (typical miss about 6 points).

## E4-1 and E4-3 results (2026-10-23)

- **Lineups (`sim/lineup.py`):** greedy narrowest-slot-first fill equals exhaustive search on 80 random rosters per slot layout and on both real rosters (Colgate 116.56, YinzBurgh 91.00 expected points for week 8; the runner-up lineup is 0.3 to 0.5 behind). K and DEF slots carry no projections until E3-7, so callers add a constant for them.
- **Standings (`sim/schedule.py`, check with `python -m fantasy.stages.validate_standings`):** recomputed from matchup scores through week 6. Win-loss-tie records match Sleeper's for all 20 teams. Points for matches exactly in Colgate; in YinzBurgh 7 of 10 teams differ from Sleeper's season total by 1 to 2 points (largest 2.00). The weekly data is internally consistent (team points equal the sum of starter points for all 120 team-weeks), so the gap is in Sleeper's own season counter, probably a stat correction after the week closed. Cause not traced. The simulator uses the weekly sums. A 1-point gap could only flip a seeding tiebreak between teams within a point of each other.
- **Seeding and bracket assumptions (unverified):** top 6 by wins, then points for, then roster id; seeds 1 and 2 get a week-15 bye; fixed bracket without re-seeding (seed 1 plays the winner of 4 v 5, seed 2 the winner of 3 v 6); weeks 15 to 17.

## E4-4 season simulator (2026-10-23)

- **Engine (`sim/season.py`):** each team-week score is `mean + persistent shift + noise_sd * z`. The persistent shift is a per-player error (QB, RB, WR 2.0 points a game, TE 1.5, provisional) that is the same in every remaining week of one simulated season. `z` is seeded per roster and week, and player errors per player, so two runs with the same seed share random numbers wherever the inputs match; that makes before-and-after comparisons (waivers, trades) far less noisy than the odds themselves. Seeding is wins, then points for, ties random; fixed 6-team bracket with seeds 1 and 2 on bye (assumption).
- **Team week model (`sim/odds.py`):** best lineup by projection for each remaining week (bye weeks drop out because they have no projection row). For the week in progress, the starters already set are used: points already scored count as realized, and only starters without points yet are simulated. Weekly variance is each player's projection times the position spread (cv, from `marginals`), with the measured same-team correlations, minus the persistent part, plus a team drift of 2 points (provisional). K and DEF are constants per slot until E3-7: K from 2023 to 2025 history for the league, DEF 8.0 mean and 25 variance (provisional).
- **Live result:** about 0.3 seconds for 20,000 simulations per league. Colgate, user's team (4-2): 75% playoffs, 24% bye, 8.7% title. YinzBurgh, user's team (3-3): 67% playoffs, 9% bye, 9.3% title.
- **Caveats:** odds assume current rosters (no future waiver moves, trades or injuries beyond the outcome spread). `tau`, the drift and the DEF constants are provisional; the calibration check (E4-6) tests team-score coverage. A started player with exactly 0 points who already played is counted as still to play (rare).
- **Tables:** `sim_season` (latest) and `sim_season_history` (archive, appended each run).

## E5-1 and E5-3 waivers and trades (2026-10-23)

- **Free agents (`sim/moves.py`):** active Sleeper players (status Active, on a team, mapped to an nflverse ID) with a projection and no roster in the league: 392 in Colgate, 385 in YinzBurgh. A first version used any projected player and offered players Sleeper doesn't list as active; the smoke test caught it.
- **Waiver shortcut:** for each of the top 10 free agents per position, add him and drop the roster's lowest remaining-season-value player, then recompute best weekly lineups; rank by extra expected points over the rest of the season. It ignores bye-week coverage and injuries, and the drop choice is a heuristic; E5-2 re-simulates the survivors for playoff and title odds. Live: Colgate's best add is Daniel Jones (QB, superflex) at +9.4 points, YinzBurgh's best is +0.5.
- **Trade evaluator:** applies the swap, keeps each team's roster size (a team that receives more players than it gives drops its lowest-value players; one that receives fewer picks up the best free agents, an assumption), then runs the season simulation before and after with the same random draws, so differences are stable. Refuses after the trade deadline (a deadline guard from E5-4 is included). Sample on real data: giving my lowest-value Colgate player for the partner's best moves my title odds from 8.6% to 15.3% and theirs from 13.3% to 6.9%.
- **Limits:** the evaluator values a trade only through projected points and the simulation; it does not model whether the partner would accept, positional scarcity beyond lineups, or injuries. K and DEF are not traded.

## E5-D2 trade builder and waivers page (2026-10-23)

- **Trades page:** pick a partner, choose players on each side, click Evaluate (an explicit button, since each run simulates). Shows both teams' playoff odds, title odds and expected wins, before and after, with signed deltas (green and red only on deltas), and lists any automatic roster moves that keep sizes equal. Refuses after the trade deadline with a message. Results are cached for 5 minutes.
- **Waivers page:** top 15 free-agent adds by extra projected points over the rest of the season (shortcut, no playoff or title odds per add yet; E5-2).
- **Bug found by running it on real data and fixed:** a trade involving a starter already set for the week in progress crashed the simulator, because the lineup kept the traded-away player. Now a traded-away starter leaves the week's lineup and acquired players start benched (regression test added). Also, the free-agent pool had included players Sleeper does not list as active.
- **Sample on real data (Colgate):** trading DJ Moore for Matthew Stafford moves my title odds from 8.6% to 13.9% and the partner's from 9.5% to 3.0% (a superflex league, so a starting QB matters a lot).
- **Test gap:** Streamlit's headless test runner crashes on multiselect widgets that use display labels (a runner bug), so the Evaluate click path is covered by calling the functions behind it, and the pages are checked to render without errors.

## Lineup page, first cut (2026-10-23)

- **What it does:** for any remaining week, the best lineup by projected points for skill positions (`data_api.lineup`), the bench, a 10-to-90% range per player from the measured scatter of actual vs projected points, and for the current week a comparison with the lineup set in Sleeper (marking Start and Sit changes). Live check: YinzBurgh's current lineup is 6.4 projected points below the best week-7 lineup, Colgate's 1.6.
- **Not done (still on the backlog):** it ignores which games have already started (E4-7), K and DEF slots (E3-7), and win probability versus an opponent (E4-2 and E4-5), so it maximizes expected points, not the chance to win. The range is shown as text, not a bar (E4-D1).

## E4-6 calibration of weekly team scores (2026-10-23)

Run with `python -m fantasy.stages.calibration`. For 120 team-weeks (weeks 1 to 6, both leagues; 108 where every skill starter had a projection), the starters actually set are given the same mean and spread the simulator uses and compared with the real score:

- **Interval coverage is right:** the 80% interval holds 83% of outcomes (Colgate 81%, YinzBurgh 86%), inside the 70 to 90% target. The 50% interval holds 56%. The predicted spread is slightly wide (standardized misses have spread 0.83, not 1.0).
- **Set lineups beat the prediction on average:** the mean standardized miss is +0.46, about 11 points per team-week. Breakdown: starters beat their projections by about 1.5 points each (about 10%), consistently by position and in weeks 1 to 5 (week 6 about 0). It is not a general bias: over all projected player-games the average miss is about zero (2026: +0.02; 2023 to 2025: -0.33, -0.06, -0.38). It is concentrated in the highest-projected players (top 8 per position-week: +1.17 in 2026 on 192 player-games, +0.29 across 2023 to 2025), so it is mostly managers starting players they know are healthy and in form, 2026 running hot so far, and a small real tendency to under-project the best players (shrinkage toward the average).
- **Effect on the odds:** the future-week lineups in the simulator are chosen by projection, not by manager information, so the selection part does not apply there; the small top-player under-projection (about +0.3 a game, about 2 points a team-week) would make every team's strength slightly low together, leaving relative odds nearly unchanged. The week in progress uses the starters actually set, so it is slightly low for everyone.
- **DEF constant fixed:** the provisional 8.0 over-predicted starting defenses (actual 6.8 to 7.0). It is now each league's measured starting-defense mean and variance from completed weeks (`MIN_DEF_ROWS` 20) until E3-7 scores defenses properly. K still comes from 2023 to 2025 history.
- **Not tested:** the persistent-error scale (tau) and the season-long spread of win totals, which need a league history this account does not have.

## End of the first working session (2026-10-23)

- **Built and pushed to `main` (about 25 commits, 97 tests):** Sleeper sync, ID crosswalk, nflverse store, per-league scoring (exact against Sleeper), baseline projections with a backtest, outcome distributions with measured correlations, lineup logic, standings and playoff seeding, Monte Carlo season odds, waiver ranking, trade evaluator, calibration check, and five dashboard pages (Home with odds, Lineup, Waivers, Trades, Outlook). The whole pipeline runs with `make refresh`.
- **Honest state of the model:** the baseline beats a trailing average on out-of-sample pinball loss (2.4% at +1 week, 4.9% at +5) but single games stay very noisy (typical miss about 6 points). Weekly team-score intervals are calibrated (80% interval holds 83%), but set lineups beat predictions by about 11 points a team-week, mostly starter selection. The odds are only as good as that: they assume current rosters and do not model injuries.
- **Provisional constants still in the code:** persistent player error (QB, RB, WR 2.0, TE 1.5), team drift 2.0, projection half-life 4, shrinkage K 3, blend 0.5, context exponent 0.5.
- **Process note:** one commit went out with a type error because a `| tail` pipe hid a failing `make check`; fixed in the next commit, and every commit since is gated on the check's real exit code (also written in `CLAUDE.md`).
- **Ticket state:** 21 story issues closed, 15 open, plus the post-MVP tracker (#37). Progress comments are on every issue. No Project board (token lacks the `project` scope).

## GitHub issues (2026-10-23)

Created in `Eliheakins/fantasy-app` from `docs/backlog.md`: 36 story issues (#1 to #36) plus a Post-MVP tracking issue (#37). Labels: epic (E0 to E5), engine or dashboard, fast-path, optional, spike, post-mvp. Milestones: one per epic. E0-3 (#3) is closed. No Project board: it needs the `project` token scope, which the personal token lacks (`gh auth refresh -s project` is interactive). The repo itself has no commits pushed yet, so the doc paths in issue bodies are plain text, not links.

## Where things are

Backlog and story IDs: `docs/backlog.md`. `docs/spec/modeling.md` sections 10b and 10c are later revisions that override its earlier sections. The original brainstorm is `docs/archive/plan.md`. The cleanup on 2026-10-23 merged the old `backlog.md` and `backlog.md`, archived `plan.md`, and corrected stale lines in `dashboard.md` and `architecture.md`.
- **Repo:** private `fantasy-app` under `Eliheakins`.

## 2026-10-23: Odds snapshots (E2-2)

- `make odds` archives raw prop-line JSON per game under `data/archive/odds/<timestamp>/`, logging credits in `credit_log.csv`. Six markets, one region (us), next 7 days of games, refuses below 100 credits left.
- Key lives in gitignored `.env` (`ODDS_API_KEY`), read by `snapshot_odds.api_key`. The user said sharing it in chat was fine.
- First snapshot: 14 games, 78 credits used, 422 left. Nothing downstream reads the files yet; the point is to build history for a later backtest.

## 2026-10-23: Locks and injuries (E4-7, #39)

- `sim/availability.py`: projections are multiplied by availability when `load_league_data` builds them, so lineup, waivers, trades and season odds all see it. Out 0, Doubtful 0.02, Questionable 0.76 for the current week only. IR, PUP, NFI, Sus and DNR are zero for 4 weeks, then full.
- Rates measured on nflverse 2018 to 2025 reports, skill players with 5 or more touches or targets the week before: 0.2% of Out, 1.8% of Doubtful, 73% of Questionable played, against 96% with no designation. 0.76 is 73 over 96.
- Known limits: expected-value scaling, not a per-week play/no-play draw in the simulation; "plays" means any touch or target, not a full workload; a game-day status says nothing about later weeks; Out is assumed to last one week.
- Locks: a team is locked once its kickoff (nflverse schedule, US Eastern) has passed, current week only. Locked starters keep their slot, locked bench players are never recommended. Greedy fill runs on the slots left over.
- Re-ran simulate: Colgate 75% playoffs, 24% bye, 9.0% title (was 8.7%).

## 2026-10-23: Player sampler and win-probability lineup (E4-2, E4-5)

- `sim/sampler.py`: Gaussian copula over measured role-pair correlations (same team and opposing, per league), marginals from the empirical quantiles of actual over projected points (levels 0.01 to 0.99). Roles are projection rank within NFL team and position. Correlation matrices are repaired to positive definite (eigenvalue floor 1e-6).
- `sim/winprob.py`: candidates are the max-points lineup, the lineup set in Sleeper, and every legal one-player swap of unlocked starter for unlocked bench player. The pick is made on the first half of 20,000 draws and win rates are reported on the second half, so choosing the best of about 40 candidates does not inflate the number.
- Confidence tag uses the paired share: of games where the chosen and max-points lineups disagree on the win, how often the chosen one wins. 70% or more is clear, 55 to 70 lean, below toss-up; identical choice reads "same as max points".
- Opponent plays the lineup set in Sleeper (current week), else their best lineup. K and DEF are league-average draws. Points already scored are not used. Injury scaling is a mean multiplier, not a play/no-play draw.
- Live result, week 7: both leagues come out "same as max points" (Colgate 53.7%, YinzBurgh 50.0%), as the one-pager predicted for most weeks.

## 2026-10-23: Waiver value by re-simulation (E5-2)

- Each shortlisted add is paired with the drop that costs the least expected points over the rest of the season (every rostered player is tried, so bye weeks and position depth count), not just the lowest-value player.
- The season is re-simulated for the top 15 adds with the same random draws as the unchanged roster. A full season run takes about 0.04 s, so this is instant.
- `se_title` is the independent-runs binomial error of the title change (about 0.3 points at 20,000 sims). Shared draws make the true error smaller, so it is an upper bound. Most title changes in week 7 are below it; playoff change is the better signal.
- Adds worth under 0.05 expected points are hidden.
- Live: Colgate's best add is Daniel Jones for J.J. McCarthy (+9.4 points, +1.6 playoff points). YinzBurgh has almost nothing on the wire.

## 2026-10-23: DEF scoring and K/DEF streaming (E3-7, E5-5)

- `stages/streaming.py` scores team defenses from nflverse team stats under each league's rules, including points-allowed and yards-allowed tiers. Points allowed exclude touchdowns the opponent's own defense and special teams scored. Checked against Sleeper DEF starters, weeks 1 to 6: 52 of 60 exact for Colgate, 41 of 60 for YinzBurgh, the rest off by 1 to 2 points (6 once). Adding `def_st_ff` on top of `ff` made it worse (27 of 60), so it stays out. Likely cause of the misses: special-teams fumble recoveries that team stats do not carry (not traced).
- Projection = form (half-life 4 games, shrink 3 games toward the league mean) plus a least-squares slope on the game's implied total (opponent's for DEF, own for K) and a dome bonus for K.
- Walk-forward test on 2024 to 2025, RMSE against the plain league average: Colgate DEF 5.60 vs 5.74, YinzBurgh DEF 5.91 vs 6.20 (small edge); K 5.21 vs 5.24 and 4.40 vs 4.40 (no edge). The Waivers page says so.
- The season simulation still uses league-average K and DEF per slot. Per-team DEF means would only move title odds slightly; not worth the plumbing yet.
- Weather is not used (nflverse has it for weeks 1 to 4 only).

## 2026-10-23: Persistent player error (tau, E3-6) and the top-player bias (#38)

- tau estimated from walk-forward residuals 2018 to 2025 with each league's scoring: variance of non-overlapping 5-game mean errors minus weekly variance over 5, floored at 0. Per league (Colgate, YinzBurgh): QB 1.41, 1.51; RB 1.62, 1.74; TE 0.45, 0.64; WR 0.63, 0.94. `TAU` is now QB 1.5, RB 1.7, WR 0.8, TE 0.55 (was 2.0, 2.0, 2.0, 1.5). Longer windows give lower values (8 games: QB 0, RB about 1, TE 0.2 to 0.6, WR 0.8 to 1.0), so persistence does not grow with horizon and 5 games is a fair middle.
- Effect on odds is small: Colgate 76.0% playoffs, 8.8% title (was 75.5%, 9.0%).
- Not tested: season win-total spread against real seasons (these leagues have no past seasons), and the estimates exclude injury-driven role changes beyond what the sample contains.
- #38: the top-8-per-position-week bias is real in direction (QB over-projected about 1 point, RB under about 0.9, TE under about 0.5, same sign in nearly every season) but pooled across positions it is +0.08 a game (2019 to 2025) and 2026's +1.17 is under 2 standard errors. Subtracting or adding the position-by-tier mean from earlier seasons cuts out-of-sample RMSE by 0.2 to 0.3% (14 of 16 cells better). Not worth the extra code; not shipped.

## 2026-10-23: Dashboard polish (E1-5, E4-D1 to E4-D3, E5-D3)

- Sidebar footer shows the age of each data source and the Sleeper and nflverse attribution. An amber banner appears when Sleeper data is over 24 hours old or NFL stats over 48.
- Lineup: range bars (10 to 90% with the projection as a dot) for the starters, and an "Optimize for" toggle (expected points or win probability) that appears only when the two lineups differ.
- Home: chance to win this week and a "Do this now" list (up to 3, in order: injured or out starters in your lineup, a lineup change, a waiver add worth at least half a point of playoff odds). Cached for 5 minutes.
- Outlook: seed distribution for my team (new `sim_seeds` table written by the simulation) and the remaining schedule with expected points and a normal-approximation win chance.
- Not done: trades never appear in "Do this now" (no partner finder yet).

## 2026-10-23: E3-8 replaced: Sleeper's own projections instead of FantasyPros ranks

- FantasyPros ranks via nflverse: the data belongs to FantasyPros and is governed by their terms, which could not be read (the terms pages render with JavaScript). Their API is personal and non-commercial only. Dropped.
- Found instead: Sleeper serves weekly stat projections (company RotoWire) at `api.sleeper.com/projections/nfl/<season>/<week>`, no key, undocumented. The stat keys match Sleeper's scoring keys, so they can be scored under each league's own rules.
- Weeks 1 to 6 of 2026, scored with each league's rules, against actual points (3,586 player-weeks, offense only): RMSE 6.01 Sleeper vs 6.26 ours (blend 5.94), MAE 4.43 vs 4.81. Correlation 0.86. Better in every position except TE (tied).
- NOT a clean test: past weeks are re-stamped the Tuesday after the games, and Sleeper's projection averaged 1.3 points for players who scored 0 versus 8.2 for those who played, which looks like inactive-player knowledge that may be after the fact. Part of the gain may be legitimate injury information, part leakage; cannot tell.
- Action: `make refresh` now archives the current week and next three (`sleeper_projections` stage, table `sleeper_proj_snapshots`, append only). After about four weeks of clean pre-game snapshots, rerun the comparison. Until then nothing uses them. Risk: undocumented endpoint, could change or disappear.

## 2026-10-23: Sleeper projections are now blended in

- The user chose to use Sleeper's projections. `sleeper_projections` also writes `proj_sleeper` (the latest snapshot scored under each league's rules; K long field goals and misses mapped from Sleeper's coarser buckets). `sim/blend.py` averages ours and Sleeper's 50/50 for the current week and the next three, for skill players (in `load_league_data`, after injury scaling, so a Questionable discount applies to our half only) and for DEF and K streaming. Later weeks stay ours.
- Equal weights are a simple choice backed by the weeks 1 to 6 comparison (blend RMSE 5.94 vs 6.01 and 6.26), which is not a clean test. #40 reruns it on pre-game snapshots; adjust the weight there.
- Effect: Colgate title odds 8.8% to 9.2%.

## 2026-10-23: Trade partner finder (planned by the ECC planner, built in this order: finder, live scoring, injury draws)

- `moves.find_trades`: one-for-one swaps of each team's top 6 players by rest-of-season points (36 per partner, about 324 per league). Stage 1 screens by `team_total` change (neither team loses more than 2 points) and keeps 8 per partner; stage 2 re-simulates them; a swap is kept when both teams' playoff plus title odds rise (playoff alone fails for a team near the ceiling, title alone is too noisy); stage 3 re-runs the 10 best on fresh draws and reports those numbers. About 1 to 2 s per league.
- `SeasonResult` gained `champion` and `made_playoffs` per run, so the Monte Carlo error of a change is the paired standard error (about 0.15 points) rather than the 0.3-point independent bound.
- Found a flaw in the existing trade and waiver evaluators while testing: the current week kept the lineup set in Sleeper, so a traded-away starter's slot was lost and the acquired player never filled it. A +12-point swap lowered playoff odds by 2 points. Fix: `build_inputs(reoptimize=True)` refills the unplayed slots (players who have scored stay put), used for both the before and after runs of `evaluate_trade`, `waiver_odds` and `find_trades`. Season odds on Home still use the lineups as set. The earlier trade-evaluator results (for example the DJ Moore for Matthew Stafford example) were affected by this.
- Live: Colgate has two trades with The Dicker Squad (Nico Collins for Tyler Shough or Lamar Jackson): you +1.2 to +1.5 playoff points, them +1.5 to +1.7. YinzBurgh has one marginal trade. Managers' acceptance is not modeled.
- Cut: two-for-one and two-for-two trades, a Pareto frontier, market values, a Home action for trades. Revisit two-for-one if the user wants more candidates before the week 11 deadline.

## 2026-10-23: Live in-week scoring

- A game's share left = 1 before kickoff, falling linearly to 0 at 200 minutes after (`sim/availability.remaining_share`). Shortcut: overtime and delays read as final early; a live game clock would fix it.
- `current_state` (used by season odds, trade, waiver and lineup math) now treats a starter as started when his game has kicked off, not when his Sleeper points are above 0. Before, a player 8 points into a game was counted as final and a finished player on 0 or negative points was simulated again. A game under way adds its remaining share of the projection to the points so far; K and DEF count by share left too (`open_k`, `open_def` are floats).
- `win_probability`: every player's column is points so far plus a draw scaled to the share left; the opponent's set starters without a projection count their actual points; K and DEF are actual plus a league-average draw for what is left. Colgate's chance to win this week went from 53.7% to 59.4% with 48.6 points already in against 0.
- `sync_week` and `data_api.refresh_live()` re-fetch the current week's matchups (two API calls); Home has a "Refresh scores" button, a live score with projected final per side, and Lineup has points-so-far and game-state columns. Scores are only as fresh as the last refresh; nothing polls.
- Not done: live game clock, season odds re-run on refresh (still from the last `simulate`), a player hurt mid-game.

## 2026-10-23: Per-week injury draws

- Step 0 (planner's check): Sleeper's projections zero Out, Doubtful and IR players but do not discount Questionable ones (week 7 mean projection against ours: 0.72 for Questionable, 0.61 for unflagged, 0.07 for Out and IR). So the availability scaling now runs after the blend and discounts both halves. `scale_projections` also returns `play_prob`.
- Current week (lineup decisions): the sampler draws play or no-play per player from his own seeded stream. Expected points stay the unconditional projection; the conditional mean is projection over p, so there is no double discount. A player whose game has started always plays (p = 1). A challenger lineup is only recommended if it also beats the max-points lineup on the held-out half (a lineup that lost there used to show as a "toss-up").
- Season simulation: for weeks after the current one, each starter has an absence path (`odds.absence_path`): out in week 0 with probability 1 minus his play chance, then a two-state chain, a healthy player misses the next week with 7% (`HAZARD`) and an absent one stays out with 55% (`STAY_OUT`), both measured on nflverse 2018 to 2025 (6.9% and 53.5%; the second is a little low because players who never return leave the sample). Draws are keyed on the player id, so a path is identical before and after a roster move and follows a traded player. When a starter is out the team loses the drop to its best replacement from the bench (`loss`), so depth is worth something in trade and waiver evaluation. Losses are added across simultaneous absences (shortcut: slightly overstates when two starters at one position are out).
- Cost: 0.15 s per season run uncached, 0.05 s with paths cached; finder and waiver runs unaffected in practice.
- Effect: Colgate playoff odds 76.8% to 78.7%, title 9.2% to 10.4%. Absences add spread, so the underdog gains. The baseline is conditional on playing, so this lowers future-week team means by about 5% for every team; relative odds move little.
- Not done: teammate usage bumps when a player is out, Friday practice status for Questionable players, weeks-out duration by injury type.

## 2026-10-23: Replacement level and positional value; trades of up to 2 for 2

User feedback: waivers asked to drop a WR for a TE or QB without valuing positions properly; a backup TE is worthless when the wire is full of them. Trades should also cover 2 for 2 and 2 for 1 either way.

- **Cause:** adds and drops were ranked by change in best-lineup points (`team_total`). It gave a bye-week TE hole +9 points, ignored that the TE could be streamed, and priced a dropped WR at his lineup points only.
- **Fix, `sim/value.py`:** every lineup slot can always be filled by a stand-in free agent: the free agents ranked below the top two at each position (the top ones are what an add would be), two per position and week, excluding anyone the roster holds. A player is worth what he adds over that floor; bye holes, absences and weak starters fall back to stand-ins. Absence damage is measured with the stand-ins in both cases, first-order per starter, weighted by the same absence chain as the simulation (`absence_probs`). A first version let stand-ins fill holes only when a starter was out and made absences look valuable; the floor design replaced it.
- `moves.Valuer` wraps it; `waiver_candidates` and `best_swap` now use it (drops are chosen among the 8 lowest rest-of-season players). The season simulation uses the same floor for team lineups in weeks after the current one and for absence losses, so waiver, trade and odds numbers agree. A player a team drops is not assumed available to it.
- **Results (week 7):** Colgate's waiver picks went from TE streamers at +9 to quarterbacks (Penix +4.4, Jones +3.9; superflex quarterbacks are scarce) with the best tight end at +1.3; YinzBurgh's best add is +0.8. `position_strength`: value over replacement per week by position with the league rank. Colgate is 1st of 10 at WR (+17.4) and 9th at QB, RB and TE; YinzBurgh is 4th to 7th everywhere. Shown on Waivers and Trades.
- **Trade finder:** now 1 for 1, 1 for 2, 2 for 1 and 2 for 2 in both directions over each team's top six (441 shapes per partner). Stage 1 screens by points, stage 2 ranks the 24 best per partner by `Valuer`, stage 3 re-simulates 6 per partner, stage 4 re-checks 10 on fresh draws. A side left with an open roster spot is compared with itself after its own waiver move (`_pickup`), so the free pickup is not credited to the trade (the issue the planner flagged). About 4 s per league.
- Season odds changed: Colgate playoffs 80.5%, title 10.8% (was 78.7%, 10.4%), because holes and byes are now filled by stand-ins instead of counting zero.
- Not done: waiver claim priority and the chance a stand-in is gone by the time of a claim; the per-position value ignores which flex slot a player fills.

## 2026-10-23: Injury model by type, practice and recovery curve

User asked what people do about injuries, noting a hamstring can linger. Common practice: expected games missed by injury type (hamstring about 2, with re-injury risk for two weeks after a return), practice participation (DNP, limited, full) as the best signal of playing, and discounting players who play through it. We measured all three on nflverse reports 2018 to 2025 instead of using rules of thumb.

- `stages/injuries.py` writes `injury_effects`: for each status (Out, Doubtful, Questionable), practice participation (Questionable only: DNP, Limited, Full) and injury type (12 common ones plus Other), the chance of playing each of the next four team games and a play-through ratio (points over projection when he plays), each cell shrunk toward its parent (30 pseudo-observations). Relevant players only (5 or more touches or targets earlier that season).
- Findings: a Questionable player plays 42% after a DNP, 66% when limited, 81% with full practice. A Questionable hamstring plays 53% this game and 69% the next; an Out hamstring is back 35%, 54% and 66% over the next three games, an Out foot 22%, 34%, 45%, groin 44%, 59%, 63%. Hamstring, ankle and illness players who play score about 6 to 10% below projection (shrunk; samples are small); other injuries are near 1.0.
- Out-of-sample (fit 2018 to 2023, scored 2024 to 2025, Brier score, lower is better), current game for Questionable and Doubtful: old constants 0.219, status-only 0.207, status plus practice plus type 0.193. For games 1 to 3 the old assumption of full health scored 0.44, 0.35, 0.29 against about 0.21 for the measured curves. Injury type adds little beyond practice and status for later games (0.2125 to 0.2117).
- `sim/injuries.py`: a flagged player gets a curve of play chances for his next four games (by his team's games, so a bye does not use up a step); `projection` is expected points counting the chance of not playing and `play_prob` holds the chance. Practice counts only once a game status has been issued (the history is of final-day practice), so early in the week Questionable players use status and type only.
- The season simulation and `Valuer` now use points-when-playing values (projection over play chance) plus the absence draws, so a flagged player is not discounted twice. While his curve lasts a single draw decides when he returns, so an absence lingers (a returned player stays back); after the four measured games the general chain (7% to miss, 55% to stay out) continues from where he was, instead of snapping to healthy. IR and similar keep zero for four games and then follow the chain too (before, they were healthy after four).
- Lineup shows "Questionable (hamstring): 55% to play, 69% next game".
- Not done: re-injury hazard in the weeks after a return (the table measures games after a flag, not after a recovery), usage change after a return, Wednesday and Thursday practice (history is final-day), a position-specific split (RBs return from hamstrings faster than WRs, per outside analysts; we did not split by position because cells get thin).

## 2026-10-23: Player outlook, what predicts improving or regressing

User asked who will improve or regress, and to research it. Research (FantasyPros-style expected points, Fantasy Footballers regression work, sticky-stat studies, rookie studies, strength-of-schedule studies): points over expected regress, target share and air yards share are the stickiest stats, rookies improve in the second half, schedule matters about half a point a game. We tested each against our own walk-forward projections (2019 to 2025) before using it, because the baseline already blends expected and actual points, weights recent games and shrinks to the position.

- **Tested, no signal beyond the baseline (out of sample, 2024 to 2025, over the next four games):** target-share and carry-share trends (correlation 0.01), opponent defense points allowed to the position (0.00 to 0.03), rookie status and week (0.02; rookies are not systematically under-projected as the season goes on, because the form already tracks their rise), the gap between actual and expected points (0.05 correlation, RMSE 3.526 to 3.521, 0.15%; the sign is that outperformers keep beating the baseline slightly, the opposite of the usual regression story, because the baseline already regresses half of it). Not modeled.
- **Found, modeled (`stages/outlook.py`, `sim/outlook.py`):**
  - Return from missed games. First game back, points over projection: after an injury report absence QB 0.82, RB 0.93, WR 0.82, TE 0.86; after an absence with no injury report (benching, role change) QB 0.41, RB 0.65, WR 0.62, TE 0.74; second game back about 0.91 to 0.98 after an injury and 0.78 to 0.93 otherwise. The first estimate pooled both kinds and overstated injury returns (0.75).
  - Teammates out. Points per unit of vacated share: WR 3.4 per target share, TE 2.5, RB 2.0 per target share and 2.5 per carry share, QB none. Share vacated is the sum of usage averages (half-life 4 games) of teammates reported Out or Doubtful (history) or whose chance of playing is below 1 (now, from the injury model).
  - Out of sample (fit 2019 to 2023, score 2024 to 2025): RMSE 6.478 to 6.417 (0.94% lower), MAE 4.93 to 4.86. First game back after a non-injury absence 5.09 to 4.07, after an injury the 1.1-point optimism disappears, teammates-out games 6.58 to 6.50, everyone else unchanged.
- Return ramps are spread across the games a flagged player may return in using his injury curve, so a player out now with a 50% chance to be back next game is ramped half in that game. `projection` stays expected points counting the chance of not playing, and play chance is kept separate, so nothing is discounted twice.
- New page "Player outlook": last four games, what usage was worth, the next four games per game when he plays, the change, a label (Improving or Regressing past 1.5 points a game, Injured when unlikely to play), and the reasons. For my roster, other rosters and free agents.
- Shortcuts: vacancy is shared equally among a team's receivers or backs (calibrated on average, ignores who absorbs most); "recent" over four games is noisy for backups; rookies, schedule and usage trends are not modeled because they tested flat here.

## 2026-10-23: Ceiling and floor in start/sit; projection calibration by size

User: starting higher-ceiling, lower-floor players in weeks projected to lose should be modeled, with an extra field or parameter. Research (variance articles, DFS tournament strategy): underdogs should take variance, floors in core spots and ceilings at flex.

- **What was already there:** the win-probability lineup (`data_api.win_probability`) already maximizes the chance to win against this week's opponent, so it takes variance when you are the underdog and protects the floor when you are favored. What it could not do was tell players apart by size: every player of a position had one shape of outcomes around his projection.
- **Per-player volatility, tested and rejected.** A player's own past spread (standard deviation of points over projection over the last 12 games, shrunk toward the position) did not improve calibration out of sample (2024 to 2025 pinball loss never beat the position shape; correlation of past spread with next-game deviation 0.07). A first test using mean absolute deviation looked strong by terciles only because high-deviation players had also been over-projected recently (their mean ratio was 0.80 to 0.87 against 1.0): the mean, not the spread, was moving.
- **Size matters, shipped.** By projection size the baseline both mis-scales and mis-shapes outcomes: a running back projected below about 6 points scores 73% to 77% of it on average with a median outcome of 40%, a 90th percentile near 1.9 times and a 10th near 0; a running back above 10 scores 105% with median 96%. Two changes, both tested out of sample (fit 2019 to 2023, scored 2024 to 2025):
  - Mean calibration by projection size (`sim/calibration.py`, `projection_calibration` table, 8 bins per league and position, piecewise linear): MAE 2.75% lower, RMSE 0.6% lower. Our baseline is calibrated before blending with Sleeper's projections (Sleeper has its own bias). The injury and outlook estimates are measured against the calibrated baseline so effects are not double-counted. This also lowers replacement-level stand-ins (low-projected free agents), and supersedes the earlier #38 conclusion for low projections.
  - Floor and ceiling shapes by size tier (`marginals` now has tier -1 for all and tiers 0 to 2 by projection thirds, measured against the calibrated projection): pinball loss 2.6% lower than one shape per position. The sampler, lineup ranges and win probability use them.
- **Start/sit changes:** the lineup search now moves through up to three successive swaps (before, single swaps only); each lineup option reports floor, median and ceiling of the team score (10th, 50th, 90th percentile, on the draws not used to pick it); a game-script label (Underdog below 45% to win, Favorite above 55%); and "Max ceiling" and "Max floor" options next to expected points and win probability. Win probability, ceiling and floor lineups are picked on half the simulated games and scored on the other half.
- **What the numbers say:** even in weeks where Colgate and YinzBurgh are underdogs (34% to 44%) no lineup beats the max-points lineup on win probability, and the ceiling lineups differ by at most one player. One flex slot is a small part of a team score that spreads about 30 points, so the variance gained is worth less than the expected points given up. The comparison table on the Lineup page shows this for each choice rather than hiding it.
