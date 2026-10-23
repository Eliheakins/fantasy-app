# Data source spikes (measured 2026-10-22)

Every number below was measured by running real calls. Scratch scripts and cached responses live in `/private/tmp/claude-501/-Users-eliheakins/f1c4f309-1847-4dfc-9529-f4531042b485/scratchpad/spikes`. Environment: Python 3.12 (uv), nflreadpy, polars, duckdb, requests. At the time of the run the real calendar was NFL week 7, regular season, and week 7 Thursday night (NE at CHI) was final.

Sleeper usage: 35 GET calls total, players file fetched once (12,229 entries, 0.5 s), no auth, no errors, no rate-limit signals.

## Summary

| Area | Verdict |
|---|---|
| A. ID crosswalk | Works. `load_ff_playerids()` has Sleeper IDs. 16 of 17 on each roster resolve; the miss is the DEF. |
| B. Projections | Does not exist as stat projections. `load_ff_rankings` is FantasyPros expert consensus rank (ECR), not projected stats. One point-like column (`r2p_pts`) exists for the current week only. |
| C. Current-season data | Works. Stats, snaps, ff_opportunity are through week 6 (last completed full week). Injuries and schedule are current. |
| D. Sleeper league data | Works. Past seasons are not reachable (no `previous_league_id`). |
| E. Scoring engine | Works. 161 of 161 resolvable offensive and kicker starters match Sleeper to the cent. DEF 17 of 19 exact. |

## A. ID crosswalk

### `load_ff_playerids()`
- Shape 12,529 rows by 35 columns. All rows have `db_season` 2026 (a single snapshot, not history).
- Columns: mfl_id, sportradar_id, fantasypros_id, gsis_id, pff_id, **sleeper_id**, nfl_id, espn_id, yahoo_id, fleaflicker_id, cbs_id, pfr_id, cfbref_id, rotowire_id, rotoworld_id, ktc_id, stats_id, stats_global_id, fantasy_data_id, swish_id, name, merge_name, position, team, birthdate, age, draft_year, draft_round, draft_pick, draft_ovr, twitter_username, height, weight, college, db_season.
- `sleeper_id` is non-null for 6,422 rows (Int64; Sleeper's JSON keys are strings, so cast).
- Contains 2026 rookies (for example Fernando Mendoza, draft_year 2026, has sleeper_id and gsis_id).
- Position values include `PK` for kickers (not `K`) and a set of IDP positions. There are 0 DEF/DST rows.
- Team abbreviations in this table are non-standard (examples seen: `GBP`, `LVR`), so do not join on team.
- Fallback tested: `dynastyprocess/data` `files/db_playerids.csv` downloads (2.6 MB), 12,529 rows, same columns, same Sleeper coverage. It is the same data as `load_ff_playerids()`, so it is not an independent fallback. It adds no coverage.

### Coverage on the user's rosters
- Colgate (roster_id 1): 17 players, 16 resolved to gsis_id, 1 failure.
- YinzBurgh (roster_id 7): 17 players, 16 resolved, 1 failure.
- Both failures are the team DEF (`CHI` in Colgate, `MIN` in YinzBurgh). Sleeper uses the team abbreviation as the player ID for a DEF (for example `"CHI"`, and starters contain `"CHI"`). The crosswalk has no DEF rows.
- No rookies, kickers, or recent signings failed on the user's two rosters.

### Coverage across the league pool
- Sleeper players with position QB/RB/WR/TE/K, status Active and a team: 760. In the crosswalk: 691 (90.9%).
- The 69 misses are 27 WR, 21 TE, 10 QB, 6 RB, 5 K. Years of experience: 33 rookies (0), 26 second-year (1), 10 others. Most are depth, practice squad, or recent signings. 5 kickers are missing, including Trey Smack (GB) and Dominic Zvada (NYG).
- Trey Smack IS in the crosswalk by name (gsis 00-0040899) but his `sleeper_id` is null. In week 6 he scored 11.8 points for a Colgate team (not the user's), and a join by Sleeper ID lost him. This is a real failure case.
- Second crosswalk source: `nflreadpy.load_rosters_weekly(2026)` has `sleeper_id` and `gsis_id` (1,988 unique Sleeper IDs, all with gsis_id). It covered 0 of the 69 misses, so it adds nothing to the union. Union coverage stays 691 of 760.
- Sleeper's own players file carries `gsis_id` for only 155 of the 760 active fantasy players. Do not rely on it.

### Needed fallback for the 9.1% gap
Match by normalized name + position + team (using `merge_name` from the crosswalk and `load_rosters_weekly` names), and keep a manual override table. This fallback was not built or tested in the spike. Only the gap was measured.

## B. Projections: `load_ff_rankings`

All three types are FantasyPros expert consensus rankings (ECR). None contains projected stat lines.

| Type | Shape | Scrape date | Content |
|---|---|---|---|
| `draft` | 5,448 x 25 | 2026-10-16 | Redraft, dynasty, and weekly ECR pages for all positions. Season-long ranks, not weekly projections. |
| `week` | 802 x 30 | 2026-10-22 | Current-week (week 7) rank pages: QB 67, RB 110, WR 160, TE 99, K 29, DST 28, plus DB, DL, LB. Kickoff timestamps run from 2026-10-23 to 2026-10-27, so this is week 7. |
| `all` | 1,862,154 x 24 | 2019-12-27 to 2026-10-16 | Historical ECR snapshots. |

Columns of `week`: page, page_pos, scrape_date, fantasypros_id, player_name, pos, team, rank, ecr, sd, best, worst, player_positions, player_short_name, player_eligibility, player_page_url, player_filename, player_bye_week, player_owned_avg, player_opponent, player_opponent_id, player_game_kickoff_ts, player_game_status, player_ecr_delta, note, tag, recommendation, pos_rank, start_sit_grade, r2p_pts.

Findings:
- Current-week 2026 data exists (week 7, scraped 2026-10-22, which is the day of the run). K and DST are covered. The `week` table has no `week` or `season` column. The week is implicit from the scrape date and the kickoff timestamps.
- Stat projection columns: none. There are no projected yards, TDs, or receptions. Per-league scoring cannot be applied to these data.
- The closest to points: `r2p_pts` ("rank to points", non-null for all 802 rows, for example Brock Purdy 20.1, top K 10.5, top DST 10.0). It is a mapping from rank to a points value, and its scoring format is not stated in the data. The page labels in `page` include `ppr-rb`, `ppr-wr`, `ppr-te`, so it looks like PPR, but this was not verified. Treat as a rough prior only. `start_sit_grade` is a letter grade (non-null for QB, RB, WR, TE, K, DST only).
- `sd`, `best`, `worst` give the spread of expert ranks. They are a rank spread, not a points distribution.
- History in `all`: weekly page types have 100 distinct weekly-qb scrape dates through 2026-10-16. There is no `week` column, only `scrape_date`, so assigning a week number requires a join to the schedule by date. This is usable for backtesting against ECR, but only as ranks.
- Freshness: `week` is same-day. `draft` and `all` are 6 days old (2026-10-16).
- Licensing: this is FantasyPros data redistributed through nflverse. The decisions log says no scraping of FantasyPros pages. Using the nflverse-hosted copy is not scraping, but redistribution terms were not checked. This needs a decision.

Implication for the plan: the "consensus blend" baseline cannot be a stat-projection blend. Stat projections must be built in-house (for example from `load_ff_opportunity` expected stats and recent usage), with ECR as a rank-based prior and a benchmark for rank accuracy only. The one-pager's open question ("does `load_ff_rankings("week")` carry current-week projections") is answered: it carries ranks, not projections.

## C. Current-season availability (2026)

All calls returned in 0.1 to 0.3 s each.

| Function | Rows | Latest week | Lag vs real calendar | Key columns |
|---|---|---|---|---|
| `load_player_stats(2026, summary_level='week')` | 6,488 x 150 | 6 | Week 7 not yet in (TNF final, but no week 7 stats rows). About one week behind. | player_id (gsis), season, week, team, opponent_team, passing_/rushing_/receiving_ yards, tds, interceptions, 2pt conversions, fumbles lost, sacks_suffered, fg_made_* by distance, `fg_made_list`, pat_made, pat_missed, fantasy_points, fantasy_points_ppr |
| `load_team_stats(2026)` | 186 x 138 | 6 | Same. Only 28 teams in week 6 (4 byes). | def_sacks, def_interceptions, fumble_recovery_opp, def_safeties, def_tds, special_teams_tds, def_fumbles_forced, def_fg_blocks, passing_yards, rushing_yards, sack_yards_lost |
| `load_snap_counts(2026)` | 8,671 x 16 | 6 | Same. | pfr_player_id (not gsis), offense_snaps, offense_pct, defense_pct, st_pct |
| `load_injuries(2026)` | 2,062 x 16 | 7 | Current. Week 7 has 273 rows: Out 7, Doubtful 1, Questionable 5, no status 260. | gsis_id, week, report_status, practice_status, report_primary_injury |
| `load_schedules(2026)` | 272 x 46 | 7 (weeks 1 to 18 exist) | Current. Week 7 TNF is already scored (home_score 30). | spread_line, total_line, home/away moneyline, roof, temp, wind, home_qb_id, away_qb_id, gametime |
| `load_depth_charts(2026)` | 684,720 x 12 | dated snapshots, latest 2026-10-22 | Current. 251 distinct snapshot days. | gsis_id, dt, team, pos_abb, pos_rank, pos_slot |
| `load_ff_opportunity(2026, 'weekly')` | 1,971 x 159 | 6 | Same one-week lag. | player_id (gsis), posteam, week, *_exp (expected stats), total_fantasy_points_exp, *_diff, *_team |
| `load_rosters_weekly(2026)` | 17,602 x 36 | 7 | Current. | gsis_id, sleeper_id, status, depth_chart_position |

Detail:
- Latest completed week in stats, snaps, team stats and ff_opportunity is 6 (week 7 is in progress). Per-week row counts for player stats: 1,118 / 1,107 / 1,114 / 1,110 / 1,057 / 982 for weeks 1 to 6. The lag is about one week, and the exact lag within a week was not measured (no timestamps were checked).
- Player stats contain 1 row with a null `player_id` in week 6. A dictionary keyed by `player_id` collides on it. This produced a wrong 0.0 for an unmapped player in the first run. Always drop null `player_id` rows.
- `load_player_stats` has no `week` filter issue, and covers K (186 rows in 2026) and every IDP position, but not DEF.
- ff_opportunity `week` column is float (1.0 to 6.0). Positions: QB, RB, WR, TE, plus OL, DL, P, null. No K and no DEF. `pbp_pass` stat type also loads (6,299 rows).

### Vegas lines and implied totals
- `spread_line` and `total_line` are present for every game through week 8 (12 of 14 week 8 games have lines), and absent for week 9 onward (0 rows). Lines per week 1 to 8: 16, 16, 16, 16, 15, 14, 14, 12.
- So team implied totals can be derived only for the current week and about the next one: implied home = (total_line - spread_line) / 2 style arithmetic, using nflverse's sign convention (`spread_line` is the home team's expected margin, positive means the home team is favored; this convention was not re-verified in the spike, so confirm it against `result` in a completed game before using it).
- Historical lines exist back to 2018 with 100% coverage in 2018 (`spread_line` non-null in all 2018 rows).
- Weather: `roof` is present for all games through week 8 (weeks 7 and 8 have some nulls). `temp` and `wind` are non-null only for weeks 1 to 4 (wind 10, 10, 13, 12 of 16 games) and 0 from week 5 onward. In 2025 `wind` is non-null for 66.7% of games. Do not rely on nflverse for weather in the K/DEF streaming rules. A separate weather source is needed, or the rule must work with `roof` and Vegas total only.

### Team defense scoring inputs
- Available per team-week in `load_team_stats`: def_sacks, def_interceptions, fumble_recovery_opp, def_fumbles_forced, def_safeties, def_tds, special_teams_tds, def_fg_blocks, def_punt_blocks, def_pat_blocks, def_2pt_made.
- Points allowed: not in team stats. Use the opponent's score from `load_schedules`. Yards allowed: use the opponent row of `load_team_stats` (passing_yards + rushing_yards, optionally plus the negative `sack_yards_lost`).
- Team abbreviations: nflverse uses `LA` for the Rams in schedules and team stats. Sleeper uses `LAR`. The crosswalk uses its own codes. A team-code map is mandatory.

### Kickers
- `load_player_stats` has per-game K rows with fg_made, fg_made_0_19 through fg_made_60_, fg_missed (also by distance), pat_made, pat_missed, and `fg_made_list` (a semicolon-separated string of made-FG distances, for example `25;44;29`). That list is required for a "points per FG yard" league rule.
- ff_opportunity and depth charts: depth charts have K (3 rows seen under `pos_abb == 'K'` in 2026, so check how kickers are listed before relying on it).

## D. Sleeper league data

Base URL `https://api.sleeper.app/v1`, GET only, no token. `/state/nfl` returned `week 7`, `season 2026`, `season_type regular`, `season_has_scores true`, `previous_season 2025`.

### League object
Fields used: `league_id`, `name`, `season`, `status` (`in_season`), `roster_positions`, `scoring_settings`, `settings`, `previous_league_id`, `draft_id`, `total_rosters`, `metadata`.

| Item | Colgate | YinzBurgh |
|---|---|---|
| roster_positions | QB, RB, RB, WR, WR, TE, FLEX, SUPER_FLEX, K, DEF, 6 BN | QB, RB, RB, WR, WR, TE, FLEX, K, DEF, 7 BN |
| num_teams | 10 | 10 |
| rec | 1.0 | 0.5 |
| pass_int | -1 | -2 |
| pass_td / pass_yd | 4 / 0.04 | 4 / 0.04 |
| K | fgm_yds 0.1 per made-FG yard, fgmiss -1, xpm 1, xpmiss -1, fgm_* distance buckets all 0 | fgm_0_19 to 40_49 = 3, 50_59 = 4, 60p = 5, fgmiss -2, xpm 1, xpmiss -1 |
| DEF | pts_allow brackets (0 = 10, 1-6 = 7, 7-13 = 4, 14-20 = 1, 21-27 = 0, 28-34 = -1, 35p = -4), yards-allowed all 0, sack 1, int 2, fum_rec 2, ff 1, safe 2, blk_kick 2 | pts_allow brackets (0 = 5, 1-6 = 4, 7-13 = 3, 14-20 = 1, 21-27 = 0, 28-34 = -1, 35p = -4), yards-allowed brackets nonzero (0-100 = 5 down to 550p = -7), def_2pt 2, ff 0 |
| playoff_teams | 6 | 6 |
| playoff_week_start | 15 | 15 |
| playoff_type / playoff_round_type / playoff_seed_type | 0 / 0 / 0 | 0 / 0 / 0 |
| trade_deadline | 11 | 11 |
| waiver_type | 0 (priority) | 0 (priority) |
| waiver_day_of_week / waiver_clear_days | 2 / 2 | 2 / 2 |
| trade_review_days | 2 | 0 |
| reserve_slots / reserve_allow_out | 1 / 1 | 1 / 1 |
| max_subs | 3 | 0 |
| settings.leg (current week) / last_scored_leg | 7 / 6 | 7 / 6 |

- The scoring_settings object is a flat dict of about 190 keys, with zeros for unused rules. All `bonus_*` keys are 0 in both leagues (no yardage or reception bonuses).
- Tiebreak settings: no named tiebreaker field was found in `settings`. Only `playoff_seed_type` (0) exists. What 0 means for seeding was not verified. Check Sleeper docs or the league UI.
- `previous_league_id` is `null` in both leagues. `/user/{id}/leagues/nfl/2025` and `/2024` return empty lists. Past seasons are not reachable through the API for these leagues. The leagues are new for 2026. The user's 2026 leagues endpoint also returns the third league (CHOPPA, out of scope).

### Matchups (`/league/{id}/matchups/{week}`)
- Fields per roster: `roster_id`, `matchup_id`, `points`, `custom_points`, `starters` (list, empty slots are the string `"0"`), `starters_points`, `players` (full roster), `players_points` (dict keyed by player ID, covers bench too).
- Week 6 (complete): user points 137.82 in Colgate and 103.86 in YinzBurgh. Week 7 (in progress): 48.62 and 17.0, which only include the Thursday game so far. Current-week points are partial until Monday night.
- A DEF appears in `starters` and `players_points` under the team abbreviation (for example `"CHI"`).
- Bye-week players and DEFs have `players_points` of 0.0.

### Rosters, transactions, other
- `/league/{id}/rosters`: 10 rosters per league. Fields: roster_id, owner_id, players, starters, reserve, taxi, settings (wins, losses, ties, fpts, fpts_against, ppts, waiver_position, waiver_budget_used, total_moves), keepers, co_owners. The user is roster 1 in Colgate (4-2, waiver_position 6) and roster 7 in YinzBurgh (3-3, waiver_position 10).
- `/league/{id}/users`: display_name, user_id, is_owner. Needed to map owner_id to a name.
- `/league/{id}/transactions/{week}`: reachable for weeks 1 to 7. Counts per week for weeks 1 to 7: Colgate 6, 17, 33, 21, 27, 20, 9. YinzBurgh 18, 16, 29, 16, 18, 26, 9. Fields: type (waiver, free_agent, trade), status (`complete`, `failed`), adds and drops (player ID to roster_id), roster_ids, creator, created (ms), leg, settings (seq, priority), metadata.notes (failure reasons such as "This player was claimed by another owner"). Failed claims are included. Filter on status.
- `/league/{id}/traded_picks`: 0 rows. `/league/{id}/drafts`: 1 draft in Colgate, 2 in YinzBurgh. `/league/{id}/winners_bracket`: returns placeholder matchups with null winners before the playoffs.

## E. Scoring engine check (week 6, 2026)

Method: for every starter on all 20 rosters (both leagues, 10 teams each), compute points from nflverse week 6 stats using that league's own `scoring_settings` (Sleeper scoring keys mapped to nflverse columns), then compare with Sleeper's `players_points`. Stat to rule mapping used: pass yards, TDs, INT, 2-pt; rush yards, TDs, 2-pt; rec, rec yards, TDs, 2-pt; fumbles lost (rushing + receiving + sack fumbles lost); sacks, completions, attempts, carries (all zero-weighted here); special-teams TDs; FG made by distance bucket; FG missed; made-FG yards parsed from `fg_made_list`; XP made and missed.

### Offense and kickers (189 starters total, 169 not DEF)
- 161 of 169 match exactly (absolute error under 0.011; observed maximum 3.6e-15, which is floating point).
- 7 starters have no row in the nflverse stat table and Sleeper shows 0.0 (bye or inactive). They are consistent: no row means zero.
- 1 failure: Trey Smack (K, GB), Sleeper 11.8, no calculation possible because the crosswalk has no Sleeper ID for him. This is a crosswalk failure, not a scoring failure. His nflverse row computes correctly once his gsis ID is known: 3 FG (25, 44, 29 yards) and 2 XP.
- The user's own 17 non-DEF starters (across both leagues): 17 of 17 exact.
- Colgate's "0.1 per made-FG yard" rule is reproduced exactly (8 of 8 resolvable Colgate kickers match) using `fg_made_list`. The per-distance columns alone cannot do this.
- No fumble, 2-point, or bonus mismatches were seen. Note the sample is one week and bonus keys are all zero, so bonuses were not exercised.

### DEF (20 starters, 19 computable, 1 on bye)
- MIN (user's YinzBurgh DEF) was on a bye. Sleeper 0.0, nflverse has no row. Consistent.
- Best variant tested (count `ff` forced fumbles when the league's `ff` is nonzero, use net yards allowed = opponent passing_yards + sack_yards_lost + rushing_yards): 17 of 19 exact. The two misses: Colgate CHI (the user's own DEF) calculated 14, Sleeper 12 (+2.0); YinzBurgh DEN calculated 11, Sleeper 12 (-1.0).
- A gross-yards variant gives 16 of 19, and omitting `ff` gives 14 of 19, so the variants matter.
- Cause of the CHI error is not proven. CHI has 3 forced fumbles in nflverse and Sleeper credited fewer. The likely cause is how Sleeper attributes forced fumbles (defense versus special teams, and the `def_st_ff` and `st_ff` keys) but this was not tested at play level.
- The DEN residual is not explained. Pending a play-by-play test.
- Wrong team code was the first DEF failure: the Rams (`LAR` in Sleeper, `LA` in nflverse) produced a false missing row until mapped.

Conclusion: per-league scoring from nflverse weekly stats is feasible for QB, RB, WR, TE, K to Sleeper's cent. DEF is within 2 points on this sample (17 of 19 exact) and needs a forced-fumble and yardage tune.

## What works
- Sleeper read-only API for leagues, rosters, matchups, transactions, users, state: fast, stable, no key.
- `load_ff_playerids()` for gsis to Sleeper mapping on 90.9% of active fantasy players.
- nflverse weekly stats, team stats, schedules (with Vegas lines), injuries, depth charts, ff_opportunity, rosters_weekly: all load in under 0.5 s each.
- Per-league scoring from nflverse stats for offense and kickers, exact.

## What does not work
- No stat projections anywhere in the checked sources. `load_ff_rankings` is ranks only.
- No past seasons of the user's leagues from Sleeper.
- No DEF rows in the ID crosswalk.
- No weather after week 4 in `load_schedules`.
- No Vegas lines beyond the next game week.

## Columns to rely on
- Join keys: Sleeper `player_id` (string) to `sleeper_id` (Int64 in the crosswalk) to `gsis_id`. nflverse player and weekly tables use `player_id` or `gsis_id` (same format, `00-00xxxxxx`). Snap counts use `pfr_player_id` and need `pfr_id` from the crosswalk.
- Stats: the `passing_*`, `rushing_*`, `receiving_*`, `fg_made_list`, `pat_*` columns of `load_player_stats`. Not `fantasy_points` or `fantasy_points_ppr` (they use fixed nflverse scoring).
- Team defense: `load_team_stats` plus `load_schedules` scores.
- Matchups: `starters`, `players_points`, `points`.
- League: `scoring_settings`, `roster_positions`, `settings.leg`, `settings.trade_deadline`, `settings.playoff_week_start`, `settings.playoff_teams`.

## Gotchas
1. Sleeper empty starter slots are the string `"0"`. A DEF is a team abbreviation string, not a numeric ID.
2. Sleeper `sleeper_id` in the crosswalk is Int64, Sleeper JSON keys are strings.
3. Team codes differ: `LAR` (Sleeper) versus `LA` (nflverse stats and schedules), and the crosswalk has its own codes (`GBP`, `LVR`). Kickers are `PK` in the crosswalk and `K` elsewhere.
4. `load_player_stats` week 6 has one null `player_id` row. Drop it before building a dict or joining.
5. Week-7 Sleeper matchup points are partial until Monday night. The nflverse stat tables lag about a week.
6. The ECR `week` table has no week column. The `all` table has no week column either, only scrape dates.
7. Depth chart history from `seasons=True` stops at 2024 (26 columns); the 2026 table has 12 columns. 2025 was not checked; the schema changed at the 2025 boundary.
8. Failed waiver claims appear in transactions (`status: failed`).
9. The 5 MB players file must be cached. It was fetched once in this spike.
10. `load_ff_opportunity` week is a float.

## Does not make sense or is risky

- **A "consensus projection blend" baseline.** The free sources give ranks, not stat projections. The plan's model policy ("beat the consensus blend") has no stat-level consensus to beat. Decide what the baseline is: rank-to-points curves, or an in-house expected-points model from `load_ff_opportunity`.
- **Using `r2p_pts` as a projection.** Its scoring format is unstated, it covers the current week only, and there is no history of it that was verified. Treat as a sanity check at most.
- **FantasyPros ECR via nflverse versus the data policy.** The decisions log forbids scraping FantasyPros pages. nflverse redistributes it. Redistribution terms were not checked. Resolve before depending on it.
- **Backtesting on the user's own leagues.** No history is reachable (no `previous_league_id`, empty 2024 and 2025 league lists). Backtests must run on nflverse history with synthetic league settings. Only the 2026 weeks 1 to 7 exist for real Sleeper-vs-model checks.
- **Weather in K/DEF streaming rules.** nflverse `temp` and `wind` are null from week 5 onward. The rule can use `roof` and the Vegas total only, unless another source is added.
- **Implied totals beyond next week.** Lines are missing from week 9 on. Multi-week lookahead for trades and playoffs cannot use Vegas lines. Use a model or a neutral prior for future weeks.
- **100% automated ID mapping.** 9.1% of active fantasy players have no match, including 5 kickers. A manual override table and a name-match fallback are required, with a loud failure for any unmapped rostered player.
- **DEF scoring exactness.** DEF is 17 of 19 on one week. Do not claim DEF parity until forced-fumble and yardage attribution is tested on more weeks and at play level.
- **Bonus rules untested.** All bonus keys are zero in both leagues, so bonus handling was not exercised. It matters only if a league adds bonuses.
- **Same-week stats freshness.** nflverse stats lag by about a week. Waiver decisions on Tuesday need week N stats that appear only after the games finish and the release runs. The exact publication time was not measured.
- **Setting lineups.** Not tested (and out of scope: read-only API). The app can recommend only.
