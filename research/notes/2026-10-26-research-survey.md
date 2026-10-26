# Research survey (2026-10-26)

After ten projection ideas failed or were explained on 2026-10-25, five research agents surveyed
what else could help: the literature, open-source models on GitHub, free outside projection
sources, prop-line methods, and simulation and evaluation practice. This note keeps their findings
and sources. What was then tested, and the numbers, are in `docs/decisions.md` (2026-10-26).
Effect sizes below are the agents' estimates unless a test is named. [unverified] marks a claim
not confirmed from the source itself.

## Starting point

The learned model is near what public box-score and play-by-play data can predict: held-out RMSE
6.0 to 6.4 against an estimated noise floor of 5.5 to 5.8, and every new feature from the same
data returned about zero. Gains left were expected from three places: what the model predicts (the
stat-less games), information the model lacks (other sources, markets, news), and how models are
judged (decisions rather than all-row RMSE).

## Literature

- **Forecast combination with few evaluation weeks.** Estimated weights are noisy and have no
  guaranteed edge over equal weights; tests have low power (Claeskens et al. 2016,
  https://repub.eur.nl/pub/81568; Frazier et al. 2023, https://arxiv.org/abs/2308.05263; Diebold
  and Shin, https://www.nber.org/papers/w24967; review: https://arxiv.org/abs/2205.04216). For the
  Sleeper weight (#40): shrink toward a prior and move only with strong evidence. Fantasy Football
  Analytics found the simple mean of sources beat every single source each year and an
  accuracy-weighted mean only tied it (vendor blog:
  https://www.r-bloggers.com/2017/03/who-has-the-best-fantasy-football-projections-2017-update/).
- **Weekly fantasy models against experts.** A 2026 Princeton thesis (Williams Jr., abstract only:
  https://theses-dissertations.princeton.edu/entities/publication/d6981488-f30c-47ce-8f06-b6c3e98f2578)
  reports XGBoost 5.4% better MAE than ESPN, with betting-market features carrying 40 to 52% of
  the gain and much of the edge from predicting who plays [unverified beyond the abstract]. The
  Wharton 2026 paper is preseason and not relevant. IBM/ESPN's news-text model reported RMSE 6.78
  on 2018 (https://arxiv.org/abs/2111.02874), not like for like.
- **Zero-heavy targets.** Zero-inflated Tweedie boosting (https://arxiv.org/pdf/1811.10192;
  https://arxiv.org/abs/2405.14990) supports a two-part model; Tweedie and Poisson losses were
  common in M5 solutions (Januschowski et al., "Forecasting with trees",
  https://cdn.amazon.science/17/31/0d99831d4add92e711a56abc75f8/forecasting-with-trees.pdf).
  Scoring functions consistent for the mean are the Bregman family (Gneiting 2011,
  https://arxiv.org/abs/0912.0902), so these losses still target the mean.
- **Hierarchical reconciliation** (Hyndman et al. 2011, https://robjhyndman.com/publications/hierarchical/;
  MinT, https://robjhyndman.com/publications/mint/): no sports application found.
- **State-space skill models.** An exponentially weighted average is the steady-state Kalman filter
  of a local-level model; Elo-type ratings as approximate Kalman filters
  (https://arxiv.org/abs/2104.14012). No evidence they beat several EWMAs.
- **Decision-based evaluation.** Score forecasts with a loss that matches the decision (Gneiting
  2011); regret against the hindsight-best decision (Elmachtoub and Grigas,
  https://arxiv.org/abs/1710.08005; survey https://arxiv.org/abs/2307.13565).

## Open-source models on GitHub

Nothing found with a clearly better held-out number than ours. Best documented:
joshuafayallen/Bayesian-Fantasy-Points-Predictor (PyMC; RMSE 6.02 RB/WR/TE and 7.57 QB on its own
2023 to 2025 folds; earlier versions mixed a limited-role and a full-time-role component, and team
strength added nothing once Vegas lines were in); cbratkovics/fantasy-football-ai (random forest,
MAE 4.49); bsr-0/nfl-player-projections (per-stat models with team-share rescaling, about 1%
better MAE than a 3-game average); FantasyFootballAnalytics/ffanalytics (multi-source scrapers and
averages); chanzer0/NFL-DFS-Tools (Gaussian copula like ours, correlations by projection window,
K and DST defaults such as DST with the opposing QB -0.30). Most repos have no licence: ideas only,
no code reuse.

## Free outside projection sources (checked 2026-10-25)

| Source | Access | Terms on scraping and storage | Decision |
|---|---|---|---|
| FFToday (`fftoday.com/rankings/playerwkproj.php`) | HTML stat lines, past weeks served, not re-stamped by the test used | No terms page; robots.txt has no directives | Used (archive stage) |
| Fleaflicker leaders | HTML, current week only, 20 rows a page | No scraping clause; robots Crawl-delay 1 | Allowed, not built |
| FantasySharks CSV | Clean CSV | Terms forbid robots, data mining and reproduction | Excluded |
| ESPN `kona_player_info` | JSON stat lines, no login | Disney terms forbid automated collection | Excluded |
| CBS projections pages | HTML stat lines | Terms forbid scraping and storing in a database | Excluded |
| FanDuel Research (numberFire) | GraphQL | Terms forbid scrapers | Excluded |
| FantasyPros consensus | 10 rows without login | Single personal copy only; login needed | Excluded |
| NFL.com fantasy | Redirects to news | n/a | Dead |
| Underdog, PrizePicks | Blocked (426, captcha) | n/a | n/a |

The rule applied is the user's (2026-10-26): a source is usable unless its terms explicitly forbid
scraping and storage.

## Prop lines

Method: de-vig two-way prices; yardage lines are medians, so mean = r_m (L + z sigma_m) with
z = Phi^-1(p_over) clamped to plus or minus 1; receptions by Poisson inversion; anytime TD
lambda = -ln(1 - p); points linear in stat means. Credit plan: one pull near kickoff per slate
(Sunday about 11:45 ET, Thursday evening), about 84 credits a week on the free 500-credit tier.
Free history: github.com/firstandthirty/nfl-tools (FanDuel via the Odds API; 2024 has passing,
rushing and receiving yards and receptions, about 34 minutes before kickoff; no licence file, used
privately under the user's rule, never committed). A prior public backtest
(github.com/gesmith0606/nfl_data_engineering) found props alone worse than Sleeper and ESPN
consensus but a small blend gain. Sources: Odds API docs (https://the-odds-api.com/liveapi/guides/v4/),
devig methods (Clarke et al. 2017,
https://www.sciencepublishinggroup.com/article/10.11648/j.ajss.20170506.12).

## Simulation and evaluation

- Open-source simulators either resample independently (ffsimulator) or use a Gaussian copula like
  ours (NFL-DFS-Tools). None found with t-copulas or game-total-conditional correlations.
- A synthetic test (gamma marginals, t-copula with 4 degrees of freedom against a Gaussian copula
  with the same rho) moved head-to-head win probability by at most 0.34 points: tail dependence
  matters for top-heavy DFS payoffs, not head-to-head. Not tested on our data.
- K and DEF correlations were unmeasured; measured on 2026-10-26 (`kdef_pairs.py`).
- Lineup regret (hindsight-best lineup minus the chosen lineup's actual points) and error near the
  flex cutoff were recommended as a second yardstick (`regret.py`).

## Ranked ideas and what happened

| Idea | Outcome (details in `docs/decisions.md`) |
|---|---|
| Two-part model for stat-less games | Tested 2026-10-26 (`hurdle_check.py`) |
| Fixed iterations or seed bagging | Fixed iterations shipped; bagging rejected |
| Lineup-regret yardstick | Built (`regret.py`) |
| Per-player residual correction | Rejected |
| Poisson loss | Rejected |
| Blend weight by shrinkage | In `blend_weight.py`; needs clean weeks |
| Outside sources | FFToday archived; equal mean with ours better on 2025 to 2026 history |
| Prop lines | Passed on 2024; build in progress |
| Vegas-total reconciliation | Rejected |
| K and DEF correlations | Measured, not used |
| Not pursued | t-copulas and game-level simulators, team-strength models, Kalman form, more box-score features |
