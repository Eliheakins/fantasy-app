# Modeling spec: scoring, projections, simulation, optimizers (E3 to E5)

> Status (2026-10-25): the learned projection (`stages/learn.py`, `projection_model = "learned"` in `config.toml`) is what the simulation reads; the rolling baseline is the fallback. Story IDs follow `docs/backlog.md`.

Status: draft v1, 2026-10-22. Scope is decisions.md and one-pager.md; nothing here reopens them. Sections 10b and 10c are later revisions and override earlier sections. Story IDs in section 10 are superseded by docs/backlog.md.
Bar: well thought out, rough execution. Every number is labeled **measured** (scratch experiment, below) or **provisional** (a starting guess to be replaced by the backtest). Upgrade paths are named, not built.

Measured experiment (nflreadpy `load_player_stats` 2021-2024 regular season, 1.0 PPR, weeks where the player's season has >= 8 games and season mean >= threshold; residual = weekly points minus the player's own season mean). Script was a throwaway in the scratchpad. Residuals taken around the season mean slightly understate spread (mean fitted in-sample) and slightly understate correlation; treat as lower-ish bounds.

| Position | Residual SD (pts) | SD / mean | Share of games < 3 pts | Skew |
|---|---|---|---|---|
| QB | 6.9 | 0.39 | 2% | 0.2 |
| RB | 7.3 | 0.55 | 7% | 0.7 |
| WR | 7.5 | 0.58 | 9% | 0.7 |
| TE | 6.0 | 0.67 | 18% | 0.9 |

| Same-team pair (weekly residual correlation) | rho | n |
|---|---|---|
| QB1 with WR1 | 0.35 | 1,902 |
| QB1 with WR2 | 0.34 | 1,675 |
| QB1 with WR3 | 0.27 | 856 |
| QB1 with TE1 | 0.30 | 1,451 |
| QB1 with RB1 | 0.08 | 1,859 |
| WR1 with WR2 | 0.02 | |
| RB1 with WR1 | -0.02 | |

Players are ranked within team by season mean, so "WR1" means the best WR by season average. These are the E3 backtest inputs for the copula and should be re-estimated by code (story E3-5), not hand-copied.

---

## 0. Conventions

- Units: fantasy points in a given league's scoring. Everything downstream of the scoring engine is per league (Colgate, YinzBurgh), never shared.
- Time: `week` is NFL week. "Now" is the first week not yet fully played. Horizon `H` = weeks `now..14` for regular season, then `15..17` for playoff weeks (6 playoff teams from week 15; see section 6).
- Data layer: parquet in, parquet out. A projection table is `(player_id_sleeper, week, source, mean, [q05,q25,q50,q75,q95 optional])`. Names below are conventions, not final column contracts.

---

## 1. Per-league scoring engine

### 1.1 Rule

Read `scoring_settings` from `GET /league/{id}` (a dict of `stat_key -> points per unit`). A player's weekly points are a dot product:

```
points = sum over stat_key in scoring_settings of  scoring_settings[stat_key] * stat_line[stat_key]
```

Implementation: build a single stat-line frame with one column per Sleeper stat key, computed from nflverse columns via a fixed mapping table (a plain dict in code), then `points = stats @ weights` using only keys present in the league's settings. Unknown keys in settings are a hard error listing the key (fail fast; do not silently score as zero). Keys with no nflverse source (e.g. long-return bonuses) are zero-filled and logged once.

### 1.2 Mapping, first pass

Sleeper key -> nflverse `load_player_stats` column:

| Sleeper | nflverse |
|---|---|
| `pass_yd`, `pass_td`, `pass_int`, `pass_2pt` | `passing_yards`, `passing_tds`, `passing_interceptions`, `passing_2pt_conversions` |
| `rush_yd`, `rush_td`, `rush_2pt` | `rushing_yards`, `rushing_tds`, `rushing_2pt_conversions` |
| `rec`, `rec_yd`, `rec_td`, `rec_2pt` | `receptions`, `receiving_yards`, `receiving_tds`, `receiving_2pt_conversions` |
| `fum_lost` | `rushing_fumbles_lost + receiving_fumbles_lost + sack_fumbles_lost` |
| `fgm_0_19 ... fgm_50p`, `fgmiss`, `xpm`, `xpmiss` | kicker columns of `load_player_stats(summary_level="week")` (`fg_made_0_19` etc.; verify names in E3-1) |
| bonus keys (`bonus_rec_te`, `bonus_pass_yd_300` etc.) | derived from the same columns with a threshold; implement only keys that appear in the two leagues |

Column names are from memory of nflreadpy; the first E3 story asserts every mapped column exists and fails otherwise.

Position-conditional keys (TE premium) are handled by multiplying by a position mask. Check whether either league has `bonus_rec_te`; if both do not, skip the mask.

### 1.3 What differs between the leagues (all from settings, no special code)

- Colgate: `rec=1.0`, `pass_int=-1`, superflex roster slot.
- YinzBurgh: `rec=0.5`, `pass_int=-2`.
- Passing TD points, yardage ratio, bonuses may also differ; the engine does not assume 4/0.04.

### 1.4 Unit check (done-when for the engine)

For 5 hand-picked player-weeks per league, the computed points equal the Sleeper matchup `players_points` value for a completed week. This catches missing keys better than any theory. Sleeper exposes `GET /league/{id}/matchups/{week}` with `players_points` and `starters_points`.

### 1.5 Projection pipeline implication

Projections are produced as **stat lines** (yards, TDs, receptions, ints) wherever the source provides them, then scored per league. If a source gives only fantasy points (some rankings do), it is converted to the league via an adjustment: `pts_league = pts_source + (rec_w_league - rec_w_source) * rec_proj + (int_w_league - int_w_source) * int_proj`, with `rec_proj` and `int_proj` taken from the usage model (section 2.3). Sources that give neither stat lines nor a known scoring basis are not used.

### 1.6 K and DEF: simple streaming rules

Decision (from decisions.md): rules, not models. They produce a mean and use the same distribution machinery as other positions with a fixed wide spread.

**Data needed for DEF scoring (per game):**
- Team DEF stat line, weekly: sacks, interceptions, fumble recoveries, defensive and special teams TDs, safeties, blocked kicks, points allowed (Sleeper keys `sack`, `int`, `ff`/`fum_rec`, `def_td`, `st_td`, `safe`, `blk_kick`, `pts_allow_0`, `pts_allow_1_6`, `pts_allow_7_13`, `pts_allow_14_20`, `pts_allow_21_27`, `pts_allow_28_34`, `pts_allow_35p`, yards-allowed tiers if present). Points allowed is the **points allowed by the defense**, i.e. opponent offensive points, which in Sleeper excludes pick-six and return TDs scored against the offense (a nuance: nflverse team points allowed includes them; subtract opponent defensive/special TDs times 6 to match, check on 5 games against Sleeper).
- Source: nflverse `load_team_stats` (sacks, interceptions, fumbles recovered, def TDs) and `load_schedules` (scores). Projected team total and spread from `load_schedules` columns `spread_line`, `total_line`, `home_rest`, `roof`, `temp`, `wind` (names to verify).
- Needed, not yet verified: `load_team_stats` carries `def_sacks`, `def_interceptions`, `def_tds`, `fumble_recovery_opp` equivalents. If not, derive from `load_pbp` (large; one-time).

**DEF projection (provisional rule, to be tuned by backtest against the opponent-agnostic mean baseline):**

```
opp_implied  = (total_line - spread_line_from_opp_view) / 2        # points the opponent is expected to score
pa_pts_mean  = interpolate tier points at opp_implied              # expectation of the PA tier points; use the Poisson-ish tier distribution below
sack_rate    = shrunk(def sacks per game, league avg, k=8 games)  * (opp_sack_rate_allowed / league_avg)
turnover_rate= shrunk(takeaways per game, league avg, k=8 games)  * (opp_giveaways / league_avg)
mean_pts = pa_tier_expectation(opp_implied) + w_sack*sack_rate + w_to*turnover_rate*(int_w+fr_w)/2 + w_td * 0.04 * 6
```
Where `pa_tier_expectation` is computed by taking opponent points ~ NegBin(mean = opp_implied, variance = 2.0 * mean) (provisional dispersion) and applying the league's tier table. Defensive/ST TD rate is a constant (provisional 0.04 per game, shrunk league average) because it is not predictable. Shrinkage constant `k` and the opponent factors are provisional; the backtest decides if they beat "season-long average DEF points".

**K projection (provisional):** `mean = E[FG attempts] * P(make by distance mix) * league FG pts + E[XP] * 1.0`. Simple version: `team_implied_total * c`, where `c` is the kicker's trailing points per implied-team-point (shrunk with k = 6 games). Dome or good weather (`roof in {dome, closed}` or wind < 10 mph, temp > 40F) adds +0.5 provisional; wind >= 15 mph subtracts 1.0 provisional. Do not model distance.

K and DEF spread: use Gamma (section 3) with CV fixed to the measured historical CV from the same kind of backtest (not measured yet; provisional CV 0.7 for DEF, 0.5 for K).

K and DEF usage: both are in the lineup optimizer as ordinary slots; they correlate with team total (negative for DEF vs opponent offense). Provisional: ignore their correlation with other players in MVP (set to independent) except DEF vs the opposing team's offense, which is handled by the game script factor in section 4.

---

## 2. Baseline weekly projections

### 2.1 Source order of preference

For player `p`, week `w`, take the first that exists:

1. **Market-implied or consensus projections for week `w`**, as stat lines, e.g. nflverse `load_ff_rankings` with weekly data if it actually carries current-week projections. **Not verified; being tested separately. The spec must work whether or not it does.**
2. Consensus ranking-derived points: convert an expert rank to expected points via a historical rank -> points curve per position (monotone isotonic fit on past weeks). Allowed only if the source is weekly ranks and no projections exist.
3. **Fallback model (must exist regardless):** a rolling expected-points model from usage (2.3).
4. For players with no usage history (rookies, new starters): position-and-depth-chart prior = mean of players at the same position and depth rank on the same team's offense type, shrunk with k = 3 games.

The baseline for the backtest is (1) if available for history, else (3). For backtest honesty, a source can be the baseline only if its history can be loaded for past weeks; a source with only current-week values cannot be walk-forward tested.

### 2.2 Blending

If more than one source exists for a player-week: simple average of league-scored points (equal weight). Do not fit blend weights in MVP (YAGNI). Upgrade path: weights by position from backtest pinball loss, then stacking in E6.

### 2.3 Fallback: rolling expected-points model

Per player, week:

```
opportunity features (last N weeks, exponentially weighted, half-life 3 games, provisional):
  RB: rush_attempts_share, target_share, snap_share, goal_line_carries  (carries inside 5, if in data)
  WR/TE: target_share, air_yards_share, snap_share, routes_run if available
  QB: dropbacks, rush attempts
team context (week w): team implied total (spread/total), pace proxy (team plays per game, trailing 6 games)

team_volume_w = team plays per game (trailing 6) scaled by implied total / league avg implied total (exponent 0.5, provisional)
player_volume = share_ewm * team_volume_w   (pass attempts, carries, targets)
yield per opportunity = shrunk(player_rate_ewm, position_league_rate, k = 40 opportunities for rate stats; k = 150 for TD rates)
stat_line = volume * yield   (per stat: attempts, yards, TDs, receptions, ints)
```
If ffopportunity expected-points data (nflverse) is available via nflreadpy (decisions.md says not verified), use expected yards/TDs per opportunity in place of the player's own trailing rates for TDs (TD regression is the largest edge in this class of model). Otherwise use own rates with the heavy k above, which is itself regression to the mean.

Opponent adjustment: multiply yield by `(opp_allowed_to_position_ewm / league_avg)` shrunk 75% to 1 (provisional; defensive matchup signal is weak in the literature and in this kind of backtest, so it must earn its place in the backtest).

Injured/inactive: if status is `Out`/`IR`/`Doubtful` the projection is 0 with probability 1 (Doubtful: 0.85 provisional), otherwise `Questionable` has `p_play` provisional 0.9, and mean is mean * p_play, with the zero mass kept in the distribution (section 3.3).

### 2.4 In-season update

- Weekly refresh on Tuesday and Thursday before TNF and Sunday morning. Pull nflverse stats, injuries, snap counts, depth charts; pull Sleeper rosters and transactions.
- EWMA features update by one game. Season-start priors blend 2 prior seasons with half-life 1 season until week 4 (the last-season rate has weight `max(0, (4 - games_this_season)/4)`).
- Bye weeks, trades, and depth-chart changes enter through the share features; there is no separate event code.
- No model refit in-season for the fallback (it is a formula). Refit only calibration constants (section 3) once per week on the most recent complete data.

---

## 3. From a point projection to a distribution

### 3.1 Interface

Input: `mean_pts` (league-scored projection mean), position, optional features. Output: a sampler `sample(n, rng, u=None)` that accepts a uniform vector `u` (for the copula, section 4) and returns points. This is the quantile function `Q_p(u)`.

### 3.2 Family per position (decision)

| Position | Family | Parameterization |
|---|---|---|
| QB | Gamma, shape `k = 1/cv^2` | mean = projection, `cv_QB = 0.39` (measured, residual SD / mean) |
| RB, WR | Zero-inflated Gamma | `P(0)` from injury/play probability only; non-zero part Gamma with `cv = 0.55` RB, `0.58` WR (measured) |
| TE | Zero-inflated Gamma | `cv = 0.67` (measured); low-end spike for blanked games: use `P(low) = 0.18 (measured share < 3 pts)` only through the lower Gamma tail, no extra spike |
| K | Gamma | `cv = 0.5` provisional |
| DEF | Shifted Gamma | floor -3 pts provisional (negative games exist), `cv` about 0.7 provisional |

Why Gamma: nonnegative, right-skew matches the measured skew (0.7 to 0.9 for skill positions), one parameter pair from mean and CV, has an inverse CDF in SciPy (`scipy.stats.gamma.ppf`) so it plugs into the copula. Negative points (fumbles, ints) are rare enough for skill positions in these leagues that truncation at 0 is accepted for MVP (known flaw; caveat in 3.5).

The mean of a player projected at `mu` is not constant CV: lower projections have higher CV (low-volume players are boom or bust). Provisional refinement tested in E3: `cv(mu) = a + b / sqrt(mu)` fitted by position on the residual table above, replacing the constant if pinball loss improves.

### 3.3 Injury and availability mixture

```
final = with prob p_play: Gamma sample ; with prob 1 - p_play: 0
```
`p_play` comes from status text mapping (provisional): Active 0.98 (always allows late scratch), Questionable 0.88, Doubtful 0.15, Out/IR 0.0. Also treat "game started and player not active" as realized zero. After kickoff, a played game is a fixed realized score (see 5.4).

### 3.4 Spread estimation

Per position, the CV is estimated from historical residuals of the baseline itself: for each past (player, week) in the backtest, residual `r = actual - projection`. Fit `cv_pos = SD(r)/mean(projection)` by position (and the `a + b/sqrt(mu)` variant). Refit each season week from the backtest table. Measured table above is a lower bound on projection error because it is vs the player's own season mean (hindsight), so a real projection's residual is wider; the first backtest run replaces those numbers and the spec's CVs are labeled as seed values.

### 3.5 Calibration checks (part of the harness, section 9)

For each position and each quantile level `tau in {0.05, 0.25, 0.5, 0.75, 0.95}`:
- **Coverage**: fraction of actuals <= predicted `Q(tau)`. Target `tau +/- 0.03`. Flag more than 0.05 off.
- **Pinball loss**: `L_tau = mean( max(tau*(y-q), (tau-1)*(y-q)) )`, averaged over `tau`. Compare to the baseline's loss (a Gamma at the same mean, with the constant seed CV).
- **PIT histogram** (probability integral transform) for one summary: ten bins, near-flat is calibrated.
- **CRPS** (decisions.md names it): compute from sample, `CRPS = mean|X - y| - 0.5 * mean|X - X'|`. Pinball over many quantiles approximates it; compute only if cheap.
- Win-probability calibration (the real output) is tested in section 9.2.

Upgrade path: replace Gamma with quantile gradient boosting per position (LightGBM `objective="quantile"`), E6.

---

## 4. Correlation

### 4.1 What matters for the decision

Win probability depends on variance of the team total, and variance depends on correlations. Stacking QB with his WR increases the variance of the sum, which helps an underdog and hurts a favorite. That is the whole reason to model it. Components:

1. **Same-team passing correlation** (QB with WR1/WR2/WR3/TE): the dominant effect.
2. **Game script** (team total and game total vs both teams): high-scoring game raises both teams' passers, lowers nothing. Negative script: trailing team passes more (WR/TE up, RB down).
3. **Opponent effects**: your QB vs opposing DEF (a DEF that scores is correlated negatively with the opposing QB). Rostering the DEF against the opponent's QB creates a built-in hedge.

### 4.2 Measured values (2021-2024, residual vs player season mean)

See table at top: QB-WR1 0.35, QB-WR2 0.34, QB-WR3 0.27, QB-TE1 0.30, QB-RB1 0.08, WR-WR ~0.02, RB-WR ~ -0.02. Teammate WR-WR near zero while each is positive with the QB is internally consistent (common factor is the QB passing output). The zero WR-WR and RB-WR are surprising only if you expect a "team shares a pie" negative; the common-factor positive and cannibalization negative roughly cancel.

Cross-team and DEF correlations: **not measured, provisional** (below).

### 4.3 Model: Gaussian copula with a structured correlation matrix

Each week, build a vector of all relevant players (both my roster and the opponent's roster, K/DEF included). Draw `z ~ N(0, R)`, set `u = Phi(z)`, and sample `x_i = Q_i(u_i)` from each player's marginal (section 3). `R` is built by rule:

```
R[i,j] = rho(type_i, type_j)  for same-team pairs, 0 for unrelated pairs
same-team pairs: QB-WR 0.34, QB-TE 0.30, QB-RB 0.08, WR-WR 0.02, WR-TE 0.02, RB-RB -0.02 (RB-RB provisional), RB-WR -0.02, RB-TE 0.0 (provisional)
opposing-team pairs (the two teams in the same game), provisional:
   QB-QB  0.10   (shared game total; shootouts)
   QB(A)-WR/TE(B) 0.10
   QB(A)-DEF(B) -0.25 (provisional, DEF scores less when the opposing QB scores a lot)
   DEF(A)-DEF(B) 0.0
   K(A)-QB(A) 0.15, K-DEF(opponent) 0.0 (provisional)
```
Ensure positive definiteness: compute the nearest PSD matrix (eigenvalue clipping then rescale to unit diagonal; 5 lines in NumPy) or add `1e-3 * I`. Because correlations are low and the structure is block-sparse, the matrix is almost always PSD; the check is a guard.

**Game total effect (simple):** add one latent factor per game, `g ~ N(0,1)`, with loading `lambda_g = 0.15` (provisional) on every non-DEF player in the game, DEF loading `-0.10`. Equivalent to adding a uniform increment to all cross-team pairs; skip it if cross-team terms above are used (do not double count). Choose the explicit pair table (above) in MVP.

### 4.4 Estimation procedure (plain, E3-5)

1. From nflverse player-week stats (4 to 8 seasons), compute league-scored points per (player, week).
2. For each player-season with >= 8 games, residual = points - mean(points over the player's season) (hindsight, fast). Better (second pass): residual vs rolling trailing-mean projection from the baseline (this matches what is used in the simulation).
3. Within (season, week, team), rank players by season mean within position (QB1, WR1..3, TE1, RB1, RB2) and compute Pearson correlation of residuals per pair type. Report n and a bootstrap 90% interval (resample weeks).
4. Rank correlation (Spearman) is the better match for a copula; compute Spearman, and Gaussian-copula parameter is `rho_g = 2 sin(pi * rho_s / 6)`. Use that value.
5. Opposing-team pairs: same, joining on `game_id` across teams.
6. Write `correlation_pairs.parquet`. Simulator reads it; the table above is the fallback until it exists.

### 4.5 Known weaknesses

- Gaussian copula has no tail dependence (all-hit games like QB 5 TD with WR 3 TD are more joint than Gaussian predicts). Acceptable for win probability near the middle; wrong for "max upside" questions. Upgrade path: t copula (add `nu = 6`), same code with a chi-square scalar.
- Correlations vary by team (pass-heavy offenses, QB-WR1 chemistry). Ignored in MVP; upgrade path: shrink team-specific estimates to the pooled value.
- Substituted QBs and injuries change structure (backup QB). Handle by rebuilding R from current depth chart every run (the "QB1" label is the current starter).

---

## 5. Win-probability lineup optimizer

### 5.1 Objective

For a given league, week, my roster `S` and opponent's `O`, choose lineup `L` (slot assignment) to maximize `P(score(L) > score(O_lineup))`, with a tie counting 0.5. This is not the same as maximizing expected points: as a favorite choose low variance, as an underdog choose high variance.

### 5.2 Opponent model

- Opponent lineup `O_lineup`: the opponent's **currently set lineup** from the Sleeper matchup endpoint (`starters` in `GET /league/{id}/matchups/{week}`), if the week has started or the lineup is set. Otherwise their best expected-points lineup by the same slot-eligibility rules (greedy by `mean`, K and DEF by `mean`). Optimal-by-mean is a defensible assumption; humans start the highest-projected players mostly.
- Opponent score samples use the same marginals and copula as mine (one joint simulation per run), so opponent players on the same team as mine are properly correlated.
- Uncertainty about the opponent's unset lineup: sample `O_lineup` among top-3 by expected points with weights 0.7/0.2/0.1 (provisional). Skip in MVP if it complicates; use best-by-mean.

### 5.3 Algorithm decision: MILP + SAA vs enumerate top-k and simulate

**Option A: MILP with sample-average approximation (SAA).** Variables: assignment `x[i,s] in {0,1}`; for each scenario `n`, win indicator `w_n` with big-M: `score_n(L) - opp_n >= -M(1 - w_n)` and `<= M w_n` plus epsilon; maximize `(1/N) sum w_n`. For N = 2,000 scenarios this is 2,000 binaries with big-M, which is a weak relaxation; HiGHS solves toy sizes but the LP bound is loose and times blow up. Exact in principle, fragile in practice.

**Option B: enumerate top-K lineups by expected points, then score each by simulation.** The roster is about 15 to 18 players; slot structure has about 8 to 10 slots. Feasible lineups number in the thousands. Generate the top K lineups cheaply by expected points (a small beam/DFS or a MILP with no-good cuts), then for each lineup compute win probability from the shared scenario matrix: `win = mean( (S[:, L].sum(1) > opp) + 0.5*(==) )`. Cost: `K x N x slots` operations, e.g. `K=500, N=10,000` is 5e6 x 9 = trivial in NumPy.

**Decision: Option B.**
- Reason 1: the set of lineups relevant to the win probability is almost always near the expected-points optimum; a lineup far from the top K by mean would have to be better on variance by more than its mean deficit allows. Using `K` large enough (500) captures every plausible variance-seeking swap.
- Reason 2: common random numbers. All K lineups are evaluated on the same scenarios, so differences between lineups are measured with much lower noise than independent runs.
- Reason 3: stays understandable. Output the top 3 lineups with win probability and the delta versus the max-expected lineup, which is exactly the dashboard card.
- Reason 4: MILP with 2,000 big-M binaries is the "too heavy" thing in section 11.

Where HiGHS still lives: the **expected-points lineup generator** is a small MILP/assignment (slot eligibility is bipartite plus FLEX, so it is a transportation problem). Top-K via repeated solves with no-good cuts (each solve excludes previous lineup as a set of `(player, slot)` pairs) is simple. Equivalent and simpler: **enumeration by DFS with pruning** on sorted players. For a 16-player roster with ~9 slots a plain recursive enumerate-with-bound on expected points is enough. Choose HiGHS for the generator only if enumeration is slower than a second. Note: the roster for lineup generation is already reduced by dropping dominated players (a player whose expected points and variance are both below another eligible player's, same slot set), which collapses the enumeration.

Upgrade path if win-probability optimum is found to differ materially from the top-500-by-points set: local search (swap one or two players) starting from the best of the K, scored on the scenario matrix. That never needs MILP.

### 5.4 Locks, injuries, in-progress games

- **Locked player** (game kicked off): his score is **realized** if the game is finished, and for a game in progress the live partial score is known: sample the remainder, `final = actual_so_far + Gamma(remaining_mean)`, remaining_mean = projection * (fraction of game left, from clock if the data exists, else 0.5). MVP: treat a started game as realized only when finished, and in progress as `actual_so_far + projection * (1 - elapsed_fraction)` with half the CV. Provisional.
- A locked player can't be moved. Constraint: fix `x[i, s_i] = 1` for locked players in their **current slot** (Sleeper slot lock behavior per slot: once a player's game starts, he's locked in the slot he occupies; moving out of a not-started slot is allowed). Pass `locked` as a dict `player -> slot`.
- **Injuries**: sampled as zero by `p_play` (3.3). That feeds the optimizer automatically: a Questionable player has a lower mean and a spike at zero, which makes him worse for a favorite and (slightly) fine for an underdog. Late-breaking news after the lineup lock cannot be handled (no API write; app only recommends).
- **Late-swap optimization (genuinely useful):** if the user's FLEX or last slot has a later game than the alternatives, a player with a later game kickoff can be left as a flex for information. Out of scope for MVP; named only.

### 5.5 Slot eligibility

Sleeper `roster_positions` is a list such as `["QB","RB","RB","WR","WR","TE","FLEX","SUPER_FLEX","K","DEF","BN",...]`. Eligibility map:

```
QB: {QB}; RB: {RB}; WR: {WR}; TE: {TE}; K: {K}; DEF: {DEF}
FLEX:        {RB, WR, TE}
SUPER_FLEX:  {QB, RB, WR, TE}
REC_FLEX:    {WR, TE}   (not in these leagues; include only if it appears)
```
Colgate has SUPER_FLEX (superflex) and 1 FLEX; YinzBurgh has 1 FLEX and no superflex. The slot list is read from the league, never hard coded. A slot `BN` and `IR` and `TAXI` never score.

Feasibility as a bipartite assignment: player -> slot with eligibility and each slot gets one player. The enumerator picks the specific slot for flex-eligible players so a lineup is a set of `(slot -> player)` pairs; to avoid duplicates from slot symmetry (two RB slots), canonicalize by treating identical slot types as unordered.

Superflex matters strategically: a second QB in the superflex slot is worth much more than in a normal league; the expected-points ranking handles it because QB means are higher. No special rule.

---

## 6. Season simulation

### 6.1 Inputs from Sleeper

- Schedule: `GET /league/{id}/matchups/{week}` for weeks 1..14 returns `roster_id` and `matchup_id` pairs, giving the weekly pairing. Past weeks give scores; future weeks give pairings only (if the API publishes them; if future matchups are not returned, derive the schedule from the league's `settings.playoff_week_start` and repeat the schedule structure only if the commissioner uses it; the fallback is to ask the user to paste it. Not verified that future weeks are returned.)
- Standings: from `GET /league/{id}/rosters`: `settings.wins`, `settings.losses`, `settings.ties`, `settings.fpts`, `settings.fpts_decimal`, `settings.fpts_against`.
- Playoff start week and number of playoff teams: `settings.playoff_week_start` and `settings.playoff_teams` (6 per the brief), trade deadline `settings.trade_deadline` (11).

### 6.2 Tiebreakers

Sleeper default: record, then points for (`fpts`). Playoff seeding: wins then points for. Sleeper has a commissioner setting for a tiebreaker (`settings.playoff_seed_type`; verify the field name) and it can be head-to-head. MVP: wins, then PF; if a tie remains, a random coin flip. Document as a known limitation; H2H tiebreaker named as an upgrade.

### 6.3 Weekly game model for the rest of season

Per remaining regular-season week, for each matchup, simulate each team's score. To stay lean, **do not simulate every player in every future week**. Use a team-week score model:

```
team_score_{t,w} ~ Normal( mu_{t,w}, sigma_{t,w} )
mu_{t,w}   = sum of starters' projected points for the week from an auto-lineup (greedy by mean) for roster t, week w, using baseline projections and bye weeks
sigma      = sqrt(sum var_i + 2 sum cov_ij)   using the same marginals and copula-based covariance
```
Measured nothing yet on team-level sigma; reference expectation is about 20 pts SD (provisional) for a 9-starter team. Use the player-level variance from section 3 plus the structured covariance to get a team sigma, and take the Normal approximation for rest-of-season weeks (a Normal for a sum of ~9 positively dependent Gammas is adequate; skew is minor at this level).

For **the current week only**, use the full player-level simulation (section 5) for my team and opponent; this is where decisions are made.

Rosters of other teams are assumed fixed for the rest of the season (their current roster, auto lineup). Waiver churn and injuries are ignored beyond the p_play factor. Provisional improvement: for every team add a small week-to-week roster drift `sigma_drift = 2 pts` independent per team-week.

### 6.4 Playoffs

Top 6 by (wins, PF) qualify; seeds 1 and 2 get a bye in a 6-team bracket in the standard format: round 1 (week 15): seed 3 v 6, 4 v 5; round 2 (week 16): seed 1 v lower remaining, seed 2 v the other (re-seed or fixed bracket per league settings; MVP assumes **re-seed off, fixed bracket**: 1 v winner(4/5), 2 v winner(3/6)); final (week 17). **Verify bracket and bye with the leagues' `settings.playoff_type` and `playoff_round_type`**. Playoff games use the same team-week Normal model with playoff-week projections (assuming roster fixed).

`P(title)` = fraction of simulations where the team wins the final. `P(playoffs)` = fraction in the top 6. Also report `P(bye)` and expected final rank.

### 6.5 Simulation count

- 20,000 simulations for the season (cheap: a few matchups x 3 to 14 weeks; vectorized NumPy, a full run takes seconds).
- Monte Carlo SE at p = 0.1 and N = 20,000 is 0.0021 (0.2 percentage points). That is the resolution floor. Use **common random numbers** for decision comparisons (waiver, trade): the baseline and the changed scenario use the same random draws, which cuts the SE of the *difference* by about 5x or more (the usual CRN gain; provisional 5x).
- Increase to 100,000 when ranking waiver candidates whose deltas are under 0.5 pts of probability.

### 6.6 Outputs

Per team: P(playoffs), P(bye), P(title), expected wins, rank distribution. Per week for my team: `P(win)`. These feed the Outlook panel.

---

## 7. Waiver ranking

### 7.1 Definition

For candidate add `a` (a free agent) and drop `d` (a roster player) in a league, value = the change in my team's outcome:

```
V(a, d) = lambda_playoff * (P_playoff' - P_playoff)
        + lambda_title   * (P_title'   - P_title)
        + lambda_week    * (P_win_this_week' - P_win_this_week)
```
Provisional weights: `lambda_title = 1.0`, `lambda_playoff = 0.5`, `lambda_week = 0.0` early season. If only one week matters (late season or playoff elimination games), use title and playoff only. Report the three deltas separately in the UI; the sum is the sort key.

### 7.2 Lean horizon approximation (decision)

Do not run a full re-simulation for every `(a, d)` pair. Steps:

1. **Prefilter by points above replacement over the horizon.** For each candidate `a` and each `d`, compute `delta_mu_w = marginal contribution to my auto-lineup expected points in week w` for `w` in the remaining weeks (including byes and playoff weeks 15 to 17; weight playoff weeks 1.5x, provisional), using the lineup greedy with and without the swap. Sum to `Delta_mu`. Keep the top 10 `(a, d)` pairs per candidate and top 30 candidates overall.
2. **Re-simulate only the survivors** (CRN) with section 6, where my team's weekly `mu` changes by `delta_mu_w` and sigma by the new composition. Cost: a few dozen full season sims (seconds each).
3. Rank by `V`.

This approximates the add's value as a change in mean team score with unchanged distribution shape, which is fine for adds that shift the mean by a few points and is wrong when the add is a boom-or-bust handcuff (variance matters), in which case use step 2's sigma update (it is included).

### 7.3 Specific rules

- **Priority waivers:** the claim only resolves if my priority beats others for the same player; the app cannot see others' claims. Show "value if the claim hits"; add a note listing league waiver priority order from `GET /league/{id}/rosters` (`settings.waiver_position`) so the user sees what priority they consume (priority resets to the back when a claim succeeds in standard Sleeper priority). Cost of using priority: provisional flat penalty of `0.1 * V(top candidate in a typical week)`; MVP does not model it. Name it.
- **Drop cost:** the dropped player is gone; the model handles it through `d`. Suggest the best `d` per `a`, not only the lowest-projected.
- **Streaming K and DEF:** same machinery. A DEF add is valued at the week-by-week cost (opponent factors change weekly); show next 3 weeks.
- **Horizon:** for the rest of the season, the weeks beyond the schedule use the baseline's constant projection (no re-forecast of ROS); decays of values are accepted.
- **Rookie and handcuff stashes:** value only through p_play-weighted mean in the injured starter's weeks; a handcuff's value is the probability his starter goes out times the replacement value. MVP: ignore this and say so.

---

## 8. Trade analyzer

### 8.1 Valuation by outcome

For a proposed trade (my set `G` gives, receive set `R`), recompute my roster, auto lineup per week, and run the same season simulation (section 6) with CRN. Output for **both** teams: `delta P_playoff`, `delta P_title`, and `delta expected wins`. Trades must satisfy roster size limits (add `drops` automatically: suggest the dropped players by the lowest value, one per excess slot).

### 8.2 Redraft specifics

- **No pick values** and no multi-year value: only rest-of-season production matters. This removes the hardest part of trade analysis (KTC-style values), and decisions.md's data policy (no scraping KTC) is consistent.
- **Deadline:** week 11. `weeks_remaining` after the trade effective week; any trade at week 11 or earlier moves production starting the next scoring week. After deadline, the Trades panel is disabled.
- **Waiver wire as a free option:** a player traded away can sometimes be replaced from the wire; the value of an asset is points above the best available replacement at the position, not above zero. The model already computes this implicitly if the waiver pool is included in the roster-after-trade (use "best free agent at position as replacement-level baseline" when the roster has an open slot; provisional simplification: replacement level = projection of the 5th-ranked free agent at the position).
- **Injured players:** `p_play` and a return-week field. An IR player returns after a known absence, valued only for the weeks he plays.
- **Contenders and sellers differ:** a team already out of the race values rest-of-season points near zero; its own `delta P_title` is about zero, so the model will say most trades are fair to it. That is realistic; the partner finder uses the AI's *expected acceptance* rather than just the title delta (below).

### 8.3 Fairness

- Both teams' `delta P_title` and `delta P_playoff`. A trade is **mutually beneficial** if both are >= `+0.5` percentage points of title or playoff probability combined (provisional threshold, `0.5 * dP_playoff + dP_title >= 0.005`).
- Fairness display: a 2-bar summary, my delta vs partner delta. A *lopsided* trade (partner delta negative by more than my gain) is flagged "unlikely to be accepted".
- Not modeling human behavior beyond that. Upgrade path: an acceptance model from ranks (positional value) is a dynasty-style epic.

### 8.4 Partner finder

For each other team `T` in the league:
1. Compute `need_T` = marginal value of one more starter at each position slot for `T`, and `surplus_T` = bench players whose removal costs `T` the least title probability (using the same weekly auto lineup).
2. Candidate trades = 1-for-1 and 2-for-1 pairs where I give from my surplus and get from T's surplus and the position is a need on the other side.
3. Prefilter by `Delta_mu` (the same horizon shortcut as waivers) on both sides; keep trades where both `Delta_mu > 0` (a positive-sum screen: both teams gain expected starter points because each fills a need). Top 50 by min of both deltas.
4. Re-simulate the survivors to get `dP_playoff` and `dP_title` for both sides; list the top 10 by `min(dV_me, dV_partner)`.

Search size is bounded: 9 teams x 15 x 15 = 2,000 1-for-1 pairs (cheap to prefilter), 2-for-1 adds a factor of ~100 (prefilter by position need first). Do 1-for-1 and 2-for-1 only.

---

## 9. Backtest harness

### 9.1 What gets tested

1. **Scoring engine**: exact agreement with Sleeper's actual `players_points` for past matchups (spot check, section 1.4).
2. **Projection point accuracy**: baseline vs candidate projections for weeks `w = 2..17` of 2022, 2023, 2024 (and 2025 if complete), walk-forward: a projection for week `w` may only use data from weeks `< w` and information available then.
3. **Distribution quality**: per position pinball loss at `tau in {.05,.1,.25,.5,.75,.9,.95}`, coverage, and PIT.
4. **Ranking quality** (what the user cares about): for each position and week, Spearman rank correlation of projection vs actual; and **start/sit regret**: for random pairs of same-position players on a hypothetical roster, how often does the higher-projected player outscore the lower (pairwise accuracy).
5. **Win-probability calibration** (after E4): use historical Sleeper league data if reachable (both leagues' completed weeks this season, any other public league matchups) for the calibration of `P(win)` vs outcomes: decile reliability curve and Brier score. Small sample (about 100 matchups per year in 2 leagues) so it is only a sanity check, not a tuned metric. Alternative that has volume: simulate synthetic matchups from nflverse stats using real players and the league's scoring and check calibration of simulated outcomes against realized points of the actual players (this tests the marginals and copula, not the opponent model).
6. **Copula check:** simulate vs realized variance of the team total sum for fixed rosters (each team's weekly sum of top-9 by season mean): compare variance ratio simulated/actual; target 0.9 to 1.1. A copula that gives the wrong total variance fails.

### 9.2 Baselines

- **Primary baseline**: consensus projection (source 1 or 2 of section 2.1) if its history is loadable; otherwise the rolling expected-points model (2.3) frozen at its first version. Name the baseline in the harness output.
- **Dumb baselines (sanity floor)**: (a) player's previous-4-week mean; (b) season-to-date mean with a prior blend. A model that does not beat these is broken.

### 9.3 Ship rule (decisions.md)

An own-built model (E6 or any alternative to the baseline, including a variant spread or correlation) ships **only if** it beats the baseline on **both** pinball loss (average over `tau`) and CRPS for the target position **in every season** of walk-forward evaluation, or in aggregate with a paired bootstrap 90% interval for the difference excluding zero (bootstrap by week). Ties go to the baseline (simpler wins). Report effect size in points of mean absolute error as well.

### 9.4 Harness shape

Single function `run_backtest(model, seasons, positions) -> metrics table` with a model as `predict(week, as_of_data) -> distribution`; every model produces the same parquet; the comparison is a Polars join of the metrics. No MLflow, no tracking server (named upgrade).

---

## 10. Story lists

Each story is sized for one working session. Done-when is one line.

### E3 Scoring engine, baseline projections, backtest, K/DEF streaming

1. **E3-1 Scoring engine.** Map Sleeper stat keys to nflverse columns; `score(stat_lines, scoring_settings)`. Done when: 5 completed player-weeks per league match Sleeper `players_points` exactly.
2. **E3-2 Historical weekly table.** Player-week and team-week table in parquet with league-scored points for both leagues (2018+ or what loads), joined to schedule (spread, total, roof, weather). Done when: any player-week is queryable with both leagues' points.
3. **E3-3 Rolling expected-points baseline.** Usage-based fallback model (section 2.3) producing stat-line projections per player-week with walk-forward safety. Done when: it emits a projection for every active player for a past week without using future data (leak test passes).
4. **E3-4 Source check and consensus ingestion.** Load `load_ff_rankings` and decide the baseline source (the spike another agent is running); convert to league scoring or rank-to-points curve. Done when: baseline source for backtests is chosen and documented in decisions.md.
5. **E3-5 Distribution and correlation estimation.** Gamma marginals with seed CVs refit by position; correlation pair table estimation (section 4.4) written to parquet with bootstrap intervals. Done when: `correlation_pairs.parquet` exists and QB-WR is within 0.05 of the measured seed table.
6. **E3-6 Backtest harness.** `run_backtest` with point and distribution metrics, coverage table, and baseline comparison. Done when: baseline and the two dumb baselines produce a metrics table for 2022 to 2024 by position.
7. **E3-7 K and DEF streaming rules.** Implement section 1.6 rules and backtest against the season-average baseline. Done when: K and DEF projections exist for the current week and the backtest table reports their pairwise ranking accuracy.

### E4 Simulation and lineup optimizer

1. **E4-1 Slot eligibility and lineup enumerator.** Read `roster_positions`; enumerate top-K lineups by expected points with FLEX/SUPER_FLEX. Done when: both leagues' current rosters give a valid best lineup and top-500 list, with locked-player constraints.
2. **E4-2 Joint scenario sampler.** Gaussian copula plus Gamma marginals with p_play mixture; `sample(N)` returns a matrix players x N. Done when: the sampled correlations and means match inputs within MC error (test).
3. **E4-3 Win-probability lineup scorer.** Opponent lineup from Sleeper matchup, CRN scoring of K lineups, top-3 report. Done when: the output shows P(win) for the best-by-points and best-by-win lineup for one league this week.
4. **E4-4 Season simulator.** Schedule, standings, tiebreakers, playoffs, 20,000 sims. Done when: P(playoffs) and P(title) sum to 6 and 1 across teams, and match a hand-checked toy league.
5. **E4-5 Calibration checks.** Copula variance ratio test and win-probability reliability curve. Done when: variance ratio is in 0.9 to 1.1 or the cause is logged.
6. **E4-6 Live lock and injury handling.** Realized scores for finished games, partial scoring in-progress, p_play from Sleeper injury status. Done when: a Sunday run reflects locked players correctly.

### E5 Waiver ranking and trade analyzer

1. **E5-1 Replacement-level and Delta_mu shortcut.** Auto-lineup greedy by week with swaps; compute `Delta_mu` over the horizon. Done when: top adds by `Delta_mu` list for both leagues.
2. **E5-2 Waiver value with CRN re-simulation.** Re-simulate survivors; value `V` and suggested drop. Done when: ranked adds show dP_playoff and dP_title with a Monte Carlo SE.
3. **E5-3 K/DEF streaming waiver view.** Next 3 weeks of K/DEF adds. Done when: the view lists top 3 streamers per slot per week.
4. **E5-4 Trade evaluator.** Evaluate a user-specified trade for both teams; roster-size handling. Done when: it prints dP_playoff and dP_title for both sides.
5. **E5-5 Partner finder.** Surplus/need screening plus re-simulation. Done when: top 10 mutually beneficial trade ideas are listed per league.
6. **E5-6 Deadline guards.** Week 11 deadline checks, post-deadline disable, injured players. Done when: the analyzer refuses after the deadline and handles an IR player.

---

## 10b. Revisions after cross-check (2026-10-23; these override earlier sections)

1. **Correlation: keep the pair-table Gaussian copula of 4.3.** A one-factor model (one shared shock per team-game) was considered and rejected. With measured QB-WR1 0.35 and QB-WR2 0.34, a single factor forces WR1-WR2 to at least 0.35 x 0.34 = 0.12 (best case, QB loading 1), but the measured value is 0.02. For a QB + WR1 + WR2 stack the variance is about 4.5% higher under one factor (SD about 2% higher), so the error is small, but the pair table costs the same code, so there is no reason to use the factor. The t-copula stays the upgrade.
2. **No optimization solver.** Slot eligibility is nested (SUPER_FLEX contains FLEX contains RB/WR/TE). Filling dedicated slots by best mean, then FLEX, then SUPER_FLEX from the leftovers is optimal for nested sets. E4-1 verifies this against brute-force enumeration on both real rosters. Top-K lineups come from per-slot alternatives near the optimum (5.3). HiGHS is dropped from the MVP, including the "expected-points lineup generator" use in 5.3; it is an option for the post-MVP partner finder.
3. **Persistent per-player error (new).** Section 6.3 treats weeks as independent, which makes P(playoffs) and P(title) overconfident because a player's projection error is shared across weeks. Draw `eps_p ~ N(0, tau_pos^2)` once per simulation per player and add it to that player's mean in every remaining week. `tau_pos` is provisional (start with 1.5 to 2.5 points per week for RB and WR) and is estimated in E3-4 as the SD of (average actual minus average projection) over windows of 5 weeks or more. E4-5 checks it against the win-total variance of past seasons.
4. **Single-matchup win probability needs no sampling for future weeks.** Under the Normal team-score model, `P(win) = Phi((mu_me - mu_opp) / sqrt(sigma_me^2 + sigma_opp^2))`. Sampling is only needed for the season simulation, where the persistent errors make weeks dependent.
5. **Opponent's lineup this week:** use the starters already set in the Sleeper matchup when the slots are filled (not `"0"`), otherwise the auto-lineup.
6. **Interactive cost:** 20,000 sims x 10 teams x at most 11 remaining weeks is about 2 million Normal draws, which takes milliseconds. The trade evaluator can run live with common random numbers. The architect's "5,000 sims" figure applies only to the post-MVP partner finder.

## 10c. Revisions after independent review (2026-10-23; override earlier sections)

7. **Estimating `tau` (fixes 10b.3).** A 5-week window mean of weekly points error carries weekly noise of about 7.3 / sqrt(5) = 3.3 points, which is larger than the 1.5 to 2.5 seed. So `tau^2 = Var(window-mean error) - sigma_week^2 / 5`, floored at 0 (log when it floors). Use `sigma_week^2 = sigma_total^2 - tau^2` in the simulator so single-week variance is unchanged and weeks are tied together only through `tau`. This avoids double counting.
8. **Dependency order.** E3-3 emits a walk-forward projection history, E3-5 builds the backtest on it, E3-6 estimates `tau` from it. `tau` can ship provisional first.
9. **Backtest comparator and horizons.** The naive comparator is a trailing mean of prior weeks, never a season average (that looks ahead). Report weeks +1 and +5 ahead; the +5 row uses neutral game context like the rest-of-season projections. Pass when the baseline beats the trailing mean on pinball loss at both horizons.
10. **Season simulation extras.** Add `sigma_drift` of 2 points per team-week (6.3). Label every odds figure "assuming current rosters". Per-player-week availability draws are a post-MVP upgrade, not MVP.
11. **Calibration.** The reliability curve is dropped: two leagues give about 70 matchups in 2026, too few per bin. Replace with team-score coverage (PIT) over all 20 teams in 2026 weeks 1 to 7 (about 140 team-weeks). The 80% interval coverage must land between 70% and 90%. The variance ratio against hindsight residuals stays only as a sampler sanity check, because it cannot see persistent error.
12. **Partial current week.** Use realized Sleeper points for games already played this week, and simulate only unplayed games. nflverse lags about a week, so it is not used for the current week.
13. **Confidence tags.** `sim_share_better` is computed on paired simulations with persistent errors included. Monte Carlo error is a footnote, not the tag.

## 11. Does not make sense or is over-built

Direct comments, ordered by severity.

1. **MILP with sample-average approximation for lineups (if anyone proposed it): over-built.** Thousands of big-M binaries with a weak relaxation, for a 9-slot problem whose answer is a small set of near-expected-optimal lineups. Use top-K enumeration plus simulation (5.3). HiGHS belongs in the expected-points generator only, or nowhere.
2. **"Use advanced math wherever feasible" vs a quantile gradient boosting model in E6: premature, and likely a loss.** The honest prior is that a consensus projection is hard to beat with free data; the one-pager already gates E6 on beating the baseline, which is the right call. Do not start E6 before the backtest has a baseline number and the baseline's calibration is known.
3. **Bayesian models (NumPyro/PyMC) listed in decisions.md: not needed for the MVP.** Shrinkage with fixed `k` (the Beta-Binomial style shrunk rate used in 2.3) is the same idea at 5% of the cost. Name the hierarchical model as the E6 upgrade.
4. **Full player-level simulation for every future week and every team: infeasible-in-spirit and unnecessary.** You do not know opponents' future lineups, injuries or waiver moves. The Normal team-score approximation (6.3) is as accurate as the inputs allow.
5. **Win-probability lineup optimization is a marginal feature in most weeks.** For most lineups the best-by-points lineup and best-by-win lineup are the same or differ in one flex slot by about 1 percentage point. The decision value is concentrated in "big underdog or favorite" weeks and in the superflex slot. The panel should say "same as max points" when that is the case, not manufacture a recommendation.
6. **Title-odds-based trade analysis for a team that is out of the race is degenerate** (it values nothing) and the mutual-benefit partner finder will produce little when both teams are contending; do not tune for this.
7. **Priority waiver modeling is not worth building.** You cannot see others' claims. Show the value if the claim hits and the priority consumed, nothing more.
8. **Correlation machinery: modest payoff.** The measured structure is one factor (QB with his pass catchers around 0.3). Cross-team, game-total, and K/DEF correlations are provisional and likely worth less than the error in the projections themselves. The copula is cheap, so keep it, but do not spend a session refining it before the calibration test (E4-5) shows the variance is wrong.
9. **Spec risks that are plans, not facts:** (a) whether Sleeper returns future-week matchups; (b) whether `load_ff_rankings` has usable projections; (c) whether ffopportunity expected points are in nflreadpy; (d) whether `load_team_stats` has DEF counting stats. Each is a spike; each has a fallback written above. Flag any failing spike in decisions.md rather than working around it silently.
10. **DEF scoring needs points allowed by the defense as Sleeper defines it, which differs from nflverse total points allowed** (return TDs). A small, easy-to-miss mismatch that would bias DEF by 1 to 2 points per game; E3-7 must check it against actual Sleeper DEF scores.
11. **Backtesting against consensus is impossible if consensus history is not loadable.** In that case the "beat consensus" gate in decisions.md degrades to "beat the frozen rolling model," and the decision log should say so rather than pretending the gate is met.
12. **Props are out of the MVP (decisions.md) and correctly so.** No spec work here.
