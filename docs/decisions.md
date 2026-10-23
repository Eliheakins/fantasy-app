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

## GitHub issues (2026-10-23)

Created in `Eliheakins/fantasy-app` from `docs/backlog.md`: 36 story issues (#1 to #36) plus a Post-MVP tracking issue (#37). Labels: epic (E0 to E5), engine or dashboard, fast-path, optional, spike, post-mvp. Milestones: one per epic. E0-3 (#3) is closed. No Project board: it needs the `project` token scope, which the personal token lacks (`gh auth refresh -s project` is interactive). The repo itself has no commits pushed yet, so the doc paths in issue bodies are plain text, not links.

## Where things are

Backlog and story IDs: `docs/backlog.md`. `docs/spec/modeling.md` sections 10b and 10c are later revisions that override its earlier sections. The original brainstorm is `docs/archive/plan.md`. The cleanup on 2026-10-23 merged the old `backlog.md` and `backlog.md`, archived `plan.md`, and corrected stale lines in `dashboard.md` and `architecture.md`.
- **Repo:** private `fantasy-app` under `Eliheakins`.
