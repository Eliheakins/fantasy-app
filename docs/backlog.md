# Backlog (2026-10-23)

One story is one working session. Engine and dashboard stories are merged per epic, so every epic ends with a usable panel. This file is canonical for story IDs and order. Story IDs in modeling.md and dashboard.md are superseded. modeling.md sections 10b and 10c override its earlier sections. Reference designs: spec/architecture.md, spec/modeling.md, spec/dashboard.md, spec/data-sources.md. Original brainstorm: archive/plan.md.

## Status (2026-10-23, end of the first working session)

**Done and verified on live data (21 issues closed):** E0-1 to E0-3, E1-1 to E1-4, E2-1, E3-1 to E3-5, E4-1, E4-3, E4-4, E4-6, E5-1, E5-3, E5-4 (deadline guard only), E5-D2. All 17 fast-path stories are done.

**Partial (issue open, first cut shipped):**
- E4-D1: Lineup page (expected-points lineup, text ranges, comparison with Sleeper). No win probability, range bars or objective toggle, and it ignores games already started.
- E4-D2: Home shows my playoff, bye and title odds. No range bars, top actions or lock state.
- E4-D3: Outlook ranks all teams and charts saved runs. No rank histogram or schedule table.
- E5-D1: Waivers page (top 15 adds). No row detail or trending.
- E3-7: DEF is each league's measured starting-defense average; K is from history. No streaming rules, no DEF scoring from team stats.

**Not started:** E1-5, E2-2 (needs a free Odds API key), E3-6 (tau is provisional), E3-8, E4-2, E4-5, E4-7, E5-2, E5-5, E5-D3.

**Known gaps:** injuries are not modeled (an Out player still projects normally); tau and the spread of season win totals are untested (no league history); DEF is an average; the highest-projected players are under-projected by about 0.3 points a game; there is no GitHub Project board (the token lacks the `project` scope).

## E0 Foundation

| ID | Story | Done when |
|---|---|---|
| E0-1 | Repo scaffold: uv with Python 3.12, `src/fantasy/` layout, Makefile, `config.toml` (user id, league ids), gitignored `data/`, first commit and push to `Eliheakins/fantasy-app` | `uv run python -c "import fantasy"` works and the push lands |
| E0-2 | `store.py`: atomic parquet write, one schema dict asserted on read and write, in-memory DuckDB views over the files | A write then read round-trips and a wrong column fails loudly |
| E0-3 | GitHub Issues created from this file (the Project board needs the `project` token scope) | Issues exist for every story |

## E1 Sleeper sync, ID crosswalk, dashboard shell

| ID | Story | Done when |
|---|---|---|
| E1-1 | `sync_sleeper`: user, leagues with settings, rosters, matchups, transactions, trending, players file (24h cache). Empty starter slots arrive as `"0"`. **Spike first:** do future weeks' matchups return pairings, and what are the playoff bracket and tiebreak settings. Record the answers in decisions.md. | Both leagues land as parquet, and the spike answers are written down |
| E1-2 | Crosswalk: Sleeper ID to nflverse ID from `load_ff_playerids`, DEF by team code with a team map (`LA` vs `LAR`), name + position + team fallback, `match_method` column, manual override table. Loud failure for any unmapped rostered player. Unmatched free agents are kept and flagged "no history". | Every player on both rosters resolves or is on the override list, and unmatched free agents are listed |
| E1-3 | Streamlit shell: navigation, league and week selectors, neutral theme, `data_api.py` stubs | App opens with four empty pages |
| E1-4 | Home roster and scoring panel on real data | Both leagues show rosters and scoring labels |
| E1-5 | Freshness footer with the "Data from Sleeper" attribution Sleeper's docs ask for when using trending data, amber stale banner, "Run sync" empty state | Deleting a parquet file shows the empty state |

## E2 NFL data store

| ID | Story | Done when |
|---|---|---|
| E2-1 | `ingest_nfl`: weekly stats, snaps, injuries, schedules (spread, total, roof), depth charts, ff_opportunity, team stats for DEF; 12h TTL; handle the null `player_id` row | Any player's history is queryable by Sleeper ID |
| E2-2 | Odds snapshot stage on the free tier: core 6 prop markets, 1 snapshot per week, archive only (needs a free API key in an environment variable). Not on the fast path, but the sooner it starts the more history it builds. | One snapshot file exists and credits used are logged |

## E3 Scoring, baseline, backtest

| ID | Story | Done when |
|---|---|---|
| E3-1 | Scoring engine: Sleeper stat keys to nflverse columns, unknown key raises | 5 completed player-weeks per league match Sleeper `players_points` exactly |
| E3-2 | Historical player-week and team-week table scored for both leagues, joined to schedule | Any player-week returns league points and game context |
| E3-3 | Rolling expected-points baseline with shrinkage. Emits a **walk-forward projection history** for every past week of the backtest seasons, plus current and rest-of-season projections (neutral game context beyond week 8). | Every active rostered player has weekly and rest-of-season projections, and the history table exists |
| E3-4 | Distributions: Gamma marginals with CV by position from walk-forward residuals. Pair-table Gaussian copula shipped as constants from modeling.md 4.3 (measured 2021 to 2024); bootstrap re-estimation is post-MVP. | Marginals and the pair table are in parquet |
| E3-5 | Backtest harness on nflverse history with synthetic 1.0 and 0.5 PPR settings. Comparator is a **trailing mean** of prior weeks (no lookahead). Reports weeks +1 and +5 ahead and coverage by position. | Baseline beats the trailing mean on pinball loss at +1 and +5, or the gap is logged and fixed |
| E3-6 | Persistent per-player error `tau` by position: `tau^2 = Var(5-week-window mean error) - sigma_week^2 / 5`, floored at 0, and the weekly sigma set so `sigma_week^2 = sigma_total^2 - tau^2` (single-week variance unchanged). Can ship with provisional values first (modeling.md 10b.3). | A tau table exists and is used by the season simulator |
| E3-7 | K and DEF streaming rules (roof and implied total only), check DEF points-allowed definition against Sleeper. Until then K and DEF use a constant per-slot average. | K and DEF projections exist for the current week |
| E3-8 (optional) | ECR rank-to-points sanity check | Blocked until the FantasyPros terms question is settled |

## E4 Simulation and lineup optimizer

| ID | Story | Done when |
|---|---|---|
| E4-1 | Slot eligibility and auto-lineup by greedy fill (dedicated slots, then FLEX, then SUPER_FLEX), plus top-K lineup enumeration. No solver. | Greedy matches brute-force enumeration on both real rosters and gives a valid lineup |
| E4-2 | Joint player-level scenario sampler (copula, Gamma marginals, play-probability mixture) for the current week | Sampled means and correlations match inputs within Monte Carlo error |
| E4-3 | Schedule, standings and playoffs from Sleeper: tiebreakers, bracket and seeding from the settings found in E1-1 | Computed standings (record, points for) match Sleeper's for games played, and seeding runs on the current table |
| E4-4 | Monte Carlo season simulator: Normal team scores with persistent per-player error (tau) and `sigma_drift` of 2 points per team-week, realized Sleeper points for games already played this week, 20,000 sims, common random numbers, weekly archive. Odds are labeled "assuming current rosters". | Playoff and title probabilities sum to 6 and 1, and match a toy league |
| E4-5 | Win-probability lineup scorer with common random numbers, opponent lineup from the starters already set in Sleeper. Outputs `sim_share_better` and the confidence tag (clear at 70% or more of paired sims, lean 55 to 70%, toss-up below 55%). Says "same as max points" when true. | Report shows win probability of both lineups with a tag |
| E4-6 | Calibration: team-score coverage (PIT) over all 20 teams in 2026 weeks 1 to 7 (about 140 team-weeks), plus a check of the sampler against the analytic formula | 80% interval coverage lands between 70% and 90%, or the cause is logged |
| E4-7 | Locks and injuries: kickoff times grey locked players, injury status with an as-of date | A player whose game started is greyed and not recommended |
| E4-D1 | Range-bar and delta helpers, Lineup view with objective toggle | Lineup matches the optimizer output row for row |
| E4-D2 | Home cards: win percent, team-total range bars, top lineup action, lock state | Both leagues show on Home |
| E4-D3 | Outlook: title odds line, rank histogram, schedule table | Both charts render, the line appears once two snapshots exist |

## E5 Waivers and trades

| ID | Story | Done when |
|---|---|---|
| E5-1 | Replacement level and the cheap mean-points shortcut for adds, using E4-1's auto-lineup. Unmatched free agents appear in a separate "no history" list. | Top adds list for both leagues |
| E5-2 | Waiver value by re-simulating survivors, with suggested drop | Adds show change in playoff and title odds with a Monte Carlo error |
| E5-3 | Trade evaluator for both sides, roster-size handling, common random numbers | Prints playoff and title odds change for both teams |
| E5-4 | Deadline guards (week 11), injured players | Analyzer refuses after the deadline |
| E5-5 (optional) | K and DEF streaming waiver view | Top 3 streamers per slot for the next 3 weeks |
| E5-D1 | Waivers view with row detail and trending | Selecting a row shows the next 4 weeks |
| E5-D2 | Trade builder and result panel, Evaluate button, amber roster warnings (no market value comparison) | Choosing assets and clicking Evaluate shows both teams' before and after odds |
| E5-D3 | Home actions merged across lineup, waiver and trade | Home shows the top 3 mixed actions per league |

## Fast path to a working trade evaluator (week 11 deadline)

17 stories: E0-1, E0-2, E1-1, E1-2, E1-3, E2-1, E3-1, E3-2, E3-3, E3-4, E3-5, E4-1, E4-3, E4-4, E5-1, E5-3, E5-D2. E3-6 (tau) ships with provisional values and is estimated afterward. E4-2 is not on the path: the trade evaluator works on team-level scores, and the player-level sampler is only for the current-week lineup scorer. Start/sit and waivers stay useful through the playoffs, but the trade tool has no value after the deadline. Whether 17 stories fit before week 11 is unknown and not estimated.

## Cut order if the budget runs short

E5-5, E3-8, E5-D3, E1-5, E4-D3, E4-7, E2-2. Keep E4-6: it is the only check that the odds are sane.

## Post-MVP

Not in the first build. Plan each after the redraft version works.

**Dynasty epic**
- Position-specific age curves (fit on nflverse career data).
- Rookie model on draft capital and athleticism.
- Draft pick valuation.
- Time-discounted asset values (win-now versus rebuild).
- Multi-year roster planning.

**FAAB expansion.** Waiver priority is the first version. FAAB adds a clearing-price model from past transactions in the league, bid sizing by dynamic programming over the remaining budget, and player value as the gain in win probability net of the opportunity cost of budget.

**CHOPPA league (16 teams, FAAB 1000).** The format is probably Chopped/guillotine (not verified), where the lowest scorer is cut each week. That changes the objective from winning matchups to surviving the cut, so it needs its own lineup optimizer. It also adds FAAB, so build it together with the FAAB expansion.

**Other**
- Partner finder (trades that help both teams) and Players search.
- Own projection model (E6): quantile gradient boosting or a hierarchical Bayesian model, shipped only if it beats the baseline and is calibrated.
- Per-player-week availability draws in the season simulation, and bootstrap re-estimation of correlations.
- Paid prop-line backfill, if backtests show props help (budget is $0 for now).
- Full K and DEF models, if the simple streaming rules turn out to matter.
- News LLM, React front end (revisit if phone access matters), draft assistant, lineup what-if.
