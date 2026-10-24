# Dashboard design spec (v1, 2026-10-23)

Scope: the local dashboard for Colgate (1.0 PPR, superflex) and YinzBurgh (0.5 PPR). Decisions in `decisions.md` and epics in `one-pager.md` are taken as given. Bar: well thought out, rough execution. This spec is a design, not a build plan with dates.

References read and applied: Stephen Few (one screen, no scrolling, data-ink, bullet graphs over gauges), Nielsen Norman Group dashboard guidance (chart choice follows the question), Geckoboard guide (hierarchy: the one number or action first, group by question), Qlik pre-attentive processing (position and length beat color; use one or two preattentive cues per screen), Tremor and shadcn blocks (KPI tile, table with badge, delta chip as the patterns to copy for a later React port). Prototype facts below were checked in a throwaway Streamlit 1.66.1 app, not guessed.

---

## 1. Design principles and visual language

### Who and what
One user, opens it a few times a week (Tuesday and Wednesday for waivers and trades, Sunday morning for lineups). Each visit has one job: "what should I do, and how much does it matter?" So the dashboard is a **decision queue with evidence**, not an analytics site.

### Principles
1. **Action first, evidence second.** Every view opens with the recommended action and its effect in win probability points. The distribution behind it sits one row below, not behind a click.
2. **Everything is a delta against doing nothing.** A swap, an add, a trade: all show change in win%, playoff%, or title%, against "keep as is". Absolute numbers are context only.
3. **Uncertainty is shown, not hidden.** Any projection that has a distribution shows the 10 to 90 range as a bar with a median tick. A recommendation that helps in fewer than 55% of paired simulations (persistent per-player errors included) gets a "toss-up" label, not a green arrow.
4. **One glanceable screen per view.** Target 1440x900 laptop, no vertical scroll for the primary content. Secondary detail goes in `st.expander` or a tab, closed by default.
5. **Color only for change.** Greys for all state. Green and red appear only on deltas (and only when the sign matters). Never on a label, a team, or a league.
6. **Two leagues, one grammar.** Same layout in both leagues. League is a global selector, not a per-view toggle. League identity comes from the name in the header, never from color.
7. **Stale data is a first-class state.** Every view shows "data as of" and a banner when the sync or the simulation is older than the last kickoff or transaction.
8. **The app recommends, it cannot set.** Sleeper's API is read-only, so every action row carries a plain-text instruction ("Start Pacheco, bench Mixon") and a link to the Sleeper league page. No fake "apply" buttons.

### Color semantics
| Use | Light | Dark | Rule |
|---|---|---|---|
| Positive delta | `#1a7f37` | `#3fb950` | Text and thin chip only, never a filled panel |
| Negative delta | `#cf222e` | `#f85149` | Same |
| Toss-up / within noise | grey `#6e7781` | `#8b949e` | Delta shown in grey with a "~" prefix |
| Warning (injury, stale) | amber `#9a6700` | `#d29922` | The only non-delta color. Used for badges and the stale banner, not for fills. A deliberate, small exception to rule 5, because injury status is a decision input. |
| Range bar fill | `#9aa5b1` | `#6e7781` | Neutral. The median tick is near-black or near-white. |
| Everything else | neutral greys | neutral greys | Accent is grey-blue `#3b4a5a`, used for selection only |

Colorblind check: green and red always travel with a sign and an arrow (`+4.1 pts`, `-2.0 pts`). Sign carries the meaning, color is redundant.

Streamlit gotcha found in the prototype: `ProgressColumn` and default buttons use `primaryColor` (red by default), which violates the color rule. Set `primaryColor` to the grey-blue in `.streamlit/config.toml`.

### Typography and density
- One sans family (Streamlit default Source Sans is fine). Tabular figures for every number column, right-aligned. Set via a small CSS injection: `font-variant-numeric: tabular-nums`.
- Size ladder, three steps only: 28 px for the single headline number per view, 14 px body and table, 12 px for captions and "as of" text.
- Density: tables are compact rows (about 32 px). 8 px spacing unit. No cards inside cards. Use `st.container(border=True)` once per panel, not nested.
- Percent formatting: win probability as whole percent (`62%`), deltas as signed points with one decimal (`+4.1`). Never show more precision than the simulation supports (50k runs, so about plus or minus 0.2 points of Monte Carlo noise at 50%).

### Light and dark
Follow the system theme (Streamlit does this by default). Do not build an in-app toggle: Streamlit cannot switch theme at runtime without hacks (see section 6). All custom colors (SVG range bars, CSS) are defined as the token pairs above, and SVGs use `currentColor` style choices where possible. Since the prototype range bar is a data-URI image, it cannot read CSS variables, so it needs two renders. Rule: generate the bar with a mid-grey fill and a median tick that stays legible on both backgrounds (`#9aa5b1` fill with `#222` tick is fine on light, weak on dark). Fix: the tick is a 3 px light-outlined dark mark. Verify once in dark mode in story D1.

### Range bars and sparklines
- **Range bar (the signature element).** A horizontal bar from p10 to p90 on a shared axis per table, with a tick at the median. Axis shared across rows so lengths compare. Axis is per table, not global. Prototype result: an SVG as a base64 data URI in `st.column_config.ImageColumn` renders correctly inside `st.dataframe` (checked by screenshot). `st.column_config` has no native range column, so the data layer returns the three numbers (`p10`, `p50`, `p90`) and a UI helper turns them into the image string. The helper is about 10 lines.
- **Team total range** on Home: same bar, two rows (me, opponent), shared axis. Overlap of the two bars is the win probability, read at a glance. This is the one place that deserves a larger (240 px) bar.
- **Sparkline** only for form (last 6 weeks of fantasy points under this league's scoring): `st.column_config.LineChartColumn` or `BarChartColumn`. Prototype: renders fine, red line by default (the theme `primaryColor` issue again).
- **Bullet-style progress** for win probability in a table: `ProgressColumn`, format `percent`, min 0 max 1. Grey fill.
- No gauges, no pie or donut charts, no 3D, no dual axis. Larger charts appear only in Outlook (line, histogram) and use the same neutral palette with one highlighted series (mine).

### Memorable detail
Every recommendation row ends with the same trio: `delta win%` chip, `range bar of the gain` is NOT shown (too heavy); instead a one-word confidence tag: `clear`, `lean`, `toss-up`, derived from the share of simulations where the change helps (>=70%, 55 to 70%, <55%). That one idea, "how often is this actually better", is what separates this from every projection-only tool, and it costs one column.

---

## 2. Views

Global frame (all views): sidebar holds the league selector (`Colgate`, `YinzBurgh`), week selector (defaults to current NFL week), and a data-freshness line. Top of main area: view title left, "as of" right, trade-deadline countdown right (`Deadline wk 11: 3 weeks`, hidden after the deadline).

Note on "Both" in the league selector: see section 6. In the spec, Home is the only view that shows both leagues at once. Every other view is single-league.

Table and column names below are the data layer's output (section 4). Names are `snake_case`, one row per entity.

### 2.1 Home

Purpose: "Do I need to do anything this week, and what?" Both leagues side by side.

```
+--------------------------------------------------------------------------------+
| Home                                   as of Wed 10:02   Deadline wk 11: 3 wks |
+--------------------------------------------------------------------------------+
| COLGATE  (1.0 PPR SF)  Wk 8        | YINZBURGH (0.5 PPR)  Wk 8                  |
|  Win prob   62%   (+4 if you act)  |  Win prob   48%   (+1 if you act)          |
|  me  |-----[==|====]------|  118   |  me  |----[===|===]-------|  104           |
|  opp |------[===|===]-----|  112   |  opp |-----[==|===]------|  107           |
|  Title 14%  Playoff 71%  Rank 3/10 |  Title 6%  Playoff 44%  Rank 6/10          |
|  ACTIONS                            |  ACTIONS                                  |
|  1 Swap Mixon > Pacheco  +4.1 clear |  1 Add Coleman, drop Hill  +1.2 lean      |
|  2 Add Jones, drop Ruiz  +0.8 toss  |  (no other actions above noise)           |
|  ALERTS                             |  ALERTS                                   |
|  ! Chase: Q, kickoff Sun 1:00       |  ! Waivers run Wed 3:00 AM (priority 4)   |
+--------------------------------------------------------------------------------+
| Slate lock: first kickoff Thu 8:15 PM  |  Players on bye: none  |  Data ok       |
+--------------------------------------------------------------------------------+
```

Elements and data:
| Element | Table | Columns |
|---|---|---|
| League header and headline number | `league_summary` | `league_id`, `league_name`, `week`, `win_prob`, `win_prob_if_act`, `playoff_prob`, `title_prob`, `rank_now`, `n_teams`, `record` |
| Team total range bars | `matchup_totals` | `league_id`, `week`, `side` (`me`/`opp`), `team_name`, `p10`, `p50`, `p90` |
| Top actions (max 3) | `actions` | `league_id`, `week`, `rank`, `kind` (`lineup`/`waiver`/`trade`), `text`, `delta_win`, `delta_title`, `confidence` (`clear`/`lean`/`toss-up`), `link_view` |
| Alerts | `alerts` | `league_id`, `severity` (`info`/`warn`), `kind` (`injury`/`lock`/`waiver_run`/`bye`/`stale`), `text`, `at_utc` |
| Footer | `data_status` | `source`, `last_refresh_utc`, `status` (`ok`/`stale`/`failed`), `detail` |

Interactions: clicking an action row jumps to the owning view with the item preselected (`st.switch_page` plus a `st.session_state` key). League header text is not a toggle. The week selector is the only control that changes content.

States:
- Loading: show the league cards with grey placeholder rows using `st.skeleton`-style empty containers (Streamlit has no skeleton, so use `st.empty()` plus a one-line "Loading simulation..." caption). Do not block the other league.
- Empty (no actions): one line "No change beats noise this week. Keep your lineup." That is a valid, useful answer.
- Partial: if simulation output is missing but sync worked (E1 only), show roster size and scoring settings in the header and the grey text "Simulation not run yet" where odds go.
- Error: per-league red-free banner (amber) with the failing source name from `data_status`.
- Offseason or bye week: "No games this week" card.

### 2.2 Lineup

Purpose: "Who do I start?" for one league and one week.

```
+--------------------------------------------------------------------------------+
| Lineup   Colgate  Wk 8     Optimize for: (o) Win prob  ( ) Points   [Refresh]   |
+--------------------------------------------------------------------------------+
| Win prob now 58%  ->  recommended 62%  (+4.1 clear)   Team proj 118 (104-132)   |
+--------------------------------------------------------------------------------+
| Slot  Player          Opp     Proj  10-90 range              Form    Status     |
| QB    Allen           @MIA    24.1  |----[==|====]-----|      ~~/\~   -         |
| SF    Goff            vs CHI  19.0  |---[=|===]------|        ~/~~    -         |
| RB1   Gibbs           vs GB   17.2  |--[===|==]-----|                 -         |
| RB2 > Pacheco   <-swap  @LV   11.3  |-[==|===]------|        ...      -         |
|       (Mixon, bench)   vs ARI  10.8                                     Q (amber) |
| WR1 ...                                                                           |
| K, DEF (streaming rule shown as text: "DEF: vs LV, dome, total 39")               |
+--------------------------------------------------------------------------------+
| Bench (collapsed expander)  |  Why this swap? (expander: correlation, sim share)  |
+--------------------------------------------------------------------------------+
```

Data:
| Element | Table | Columns |
|---|---|---|
| Header numbers | `lineup_summary` | `league_id`, `week`, `objective`, `win_prob_current`, `win_prob_recommended`, `delta_win`, `confidence`, `team_p10`, `team_p50`, `team_p90` |
| Slot table | `lineup_slots` | `league_id`, `week`, `slot`, `player_id`, `player_name`, `team`, `pos`, `opp`, `home_away`, `kickoff_utc`, `proj_p10`, `proj_p50`, `proj_p90`, `form_last6` (list of floats), `injury_status`, `is_recommended` (bool), `is_current` (bool), `swap_with_player_id`, `delta_win_if_swapped` |
| Bench | `bench_players` | same player columns plus `best_slot` |
| K/DEF note | `streaming_notes` | `league_id`, `week`, `pos`, `player_id`, `rule_text`, `vegas_total`, `weather`, `dome` |
| Why | `lineup_explain` | `league_id`, `week`, `player_id`, `sim_share_better`, `corr_note` |

Interactions:
- Objective toggle (`st.radio`, horizontal): changes `objective`, re-reads from the layer (both pre-computed, no recompute).
- Swap rows highlight the replaced player in the same row group, not a separate list. Delta chip per swap.
- Locked players (kickoff passed) are greyed and not swappable in recommendations.
- Read-only: a "Copy plain-text lineup" button (`st.code` block has a built-in copy icon, so no button needed).
- One what-if: a `st.data_editor` checkbox column "Force start" that re-queries `lineup_whatif(...)`. Optional, cut if the optimizer is not fast enough (see section 6).

States:
- Loading: table shell with headers, "Optimizing..." caption under the header numbers.
- Empty: before the lineup is available (rosters not synced), "No roster yet. Run sync." plus the command text.
- Partial: player with no projection shows `-` in range and a "no projection" badge, and is excluded from recommendations.
- Error: optimizer failed, show the last good run with an amber "from Tue 9:00" banner.

### 2.3 Waivers

Purpose: "Who should I add, and who goes?"

```
+--------------------------------------------------------------------------------+
| Waivers   YinzBurgh  Wk 8      My priority: 4 of 10     Next run: Wed 3:00 AM   |
+--------------------------------------------------------------------------------+
| #  Add            Pos  Drop         d win  d title  Conf    Proj range    Avail  |
| 1  Coleman        WR   Hill         +1.2   +0.4     lean    |--[=|==]--|  97%   |
| 2  Jones          RB   Ruiz         +0.8   +0.2     toss    |-[=|=]----|  88%   |
| 3  Dortch         WR   Hill         +0.3   +0.1     toss    ...                |
+--------------------------------------------------------------------------------+
| Selected: Coleman  | Next 4 wks: [range bars per week]  | Bye wks | Trending  |
| Claim order tip: "Claim Coleman first, then Jones as the fallback"              |
+--------------------------------------------------------------------------------+
| Trending adds on Sleeper (expander): player, adds_24h                           |
+--------------------------------------------------------------------------------+
```

Data:
| Element | Table | Columns |
|---|---|---|
| Ranked adds | `waiver_adds` | `league_id`, `week`, `rank`, `add_player_id`, `add_name`, `pos`, `team`, `drop_player_id`, `drop_name`, `delta_win`, `delta_playoff`, `delta_title`, `confidence`, `proj_p10`, `proj_p50`, `proj_p90`, `is_available`, `rostered_pct` |
| Selected detail | `waiver_add_horizon` | `league_id`, `add_player_id`, `week`, `p10`, `p50`, `p90`, `bye` |
| Priority and timing | `waiver_context` | `league_id`, `my_priority`, `n_teams`, `next_run_utc` |
| Trending | `trending_adds` | `player_id`, `player_name`, `adds_24h` |

Interactions: row selection (`st.dataframe(on_select="rerun", selection_mode="single-row")`) fills the detail strip. Sort by `delta_win` default, changeable via column header click. The horizon strip is a small `st.bar_chart` with p50 bars only (no custom range chart in the strip). With priority waivers (not FAAB), the ranking is a claim order, so the text tip is generated by the engine as `claim_order_text`.

States: empty (nothing beats noise: "No add improves your odds beyond noise."), loading (header plus empty table shell), partial (trending unavailable: expander shows "Sleeper trending unavailable"), error as in Lineup.

### 2.4 Trades

Purpose: "If I do this trade, what happens to my playoff and title odds, and theirs?"

```
+--------------------------------------------------------------------------------+
| Trades   Colgate      Deadline wk 11: 3 wks                                    |
+--------------------------------------------------------------------------------+
| Partner: [ Team Falcons v ]                                                    |
| I GIVE [multiselect: Mixon, Hill     ]  |  I GET [multiselect: Jones, Pick 2]  |
|  roster tags: RB1, WR3                  |   roster tags: WR1                   |
| [ Evaluate ]                                                                    |
+--------------------------------------------------------------------------------+
|              Me                          |            Them                      |
| Playoff   71% -> 78%  (+7.0)             | 55% -> 52%  (-3.0)                   |
| Title     14% -> 17%  (+3.0)             |  9% ->  8%  (-1.0)                   |
| Avg wins 8.1 -> 8.4                      |                                      |
+--------------------------------------------------------------------------------+
| Lineup after trade (expander)  |  Roster-slot holes created: "none"            |
+--------------------------------------------------------------------------------+
```

Data:
| Element | Table | Columns |
|---|---|---|
| Teams in league | `league_teams` | `league_id`, `roster_id`, `team_name`, `owner`, `is_me` |
| Tradable assets | `trade_assets` | `league_id`, `roster_id`, `asset_id`, `asset_name`, `pos`, `team`, `slot_role`, `kind` (`player`/`pick`) |
| Evaluation | `trade_eval` | `league_id`, `give_ids`, `get_ids`, `partner_roster_id`, `side` (`me`/`them`), `playoff_before`, `playoff_after`, `title_before`, `title_after`, `exp_wins_before`, `exp_wins_after`, `roster_warnings` |
| Optional partner finder | `trade_ideas` | `league_id`, `give_ids`, `get_ids`, `partner_roster_id`, `delta_title_me`, `delta_title_them` |

Interactions: partner picker (`st.selectbox`) filters the "I get" multiselect to that team's assets. Both multiselects hold their state in `st.session_state` keys `trade_give` and `trade_get`. An explicit Evaluate button (the call is a simulation run of seconds, not instant). Result is cached on a hash of (league, sorted give, sorted get). Both sides are shown even though only mine matters, because "would they accept" is half the decision, and the engine already computes both. Deadline countdown disables Evaluate with "Deadline passed" after week 11.

States: empty (nothing selected: "Pick at least one asset on each side"), loading (`st.spinner("Simulating 50k seasons...")`), error (invalid trade, e.g. roster size violation, shown in `roster_warnings` as amber text).

### 2.5 Outlook

Purpose: "How is my season going, and what is left?" The least urgent view, so it is the most chart-heavy, but still one screen.

```
+--------------------------------------------------------------------------------+
| Outlook   Colgate   Wk 8 of 14 regular season                                   |
+--------------------------------------------------------------------------------+
| Title 14%   Playoff 71%   Median finish 3rd   Rank 3/10                         |
+----------------------------------------+---------------------------------------+
| Title odds by week (line, my team bold,| Final rank distribution (bar, 1..10)  |
| 3 closest rivals grey)                 |  ,---.                                |
|   __/\__/-                             |  | | |  ||                             |
+----------------------------------------+---------------------------------------+
| Rest-of-season schedule: opp, opp rank, win prob per week  [range sparkline]    |
| Wk9 vs Falcons 58% | Wk10 @ Bears 51% | ... | Strength of schedule 4th easiest   |
+--------------------------------------------------------------------------------+
```

Data:
| Element | Table | Columns |
|---|---|---|
| Headline | `season_summary` | `league_id`, `week`, `title_prob`, `playoff_prob`, `median_rank`, `rank_now`, `record` |
| Title odds over time | `odds_history` | `league_id`, `roster_id`, `week`, `title_prob`, `playoff_prob`, `snapshot_utc` |
| Rank histogram | `rank_distribution` | `league_id`, `roster_id`, `final_rank`, `prob` |
| Schedule | `schedule_ahead` | `league_id`, `week`, `opp_roster_id`, `opp_name`, `opp_rank`, `win_prob`, `is_playoffs` |
| SOS | `schedule_strength` | `league_id`, `roster_id`, `sos_rank`, `sos_score` |

`odds_history` only exists if the pipeline snapshots odds every week. It starts empty at the first run (see "Does not make sense" below).

Interactions: a "Compare" `st.multiselect` of up to 3 rivals for the line chart (default: top 3 by title odds). Hover tooltips come from the chart library. No league "Both".

States: empty history ("One snapshot so far. The line appears next week."), loading, error.

### 2.6 Players search (include, small)

Justified because every other view is a recommendation list; the user will often ask "what about player X?" (a name on the waiver wire not in the top 10, a trade target). One search box, one page.

```
+--------------------------------------------------------------------------------+
| Players   Colgate   [ search name...      ]                                     |
+--------------------------------------------------------------------------------+
| Jaylen Waddle  MIA WR   Rostered by: Falcons   Proj wk8: |--[=|==]--|  Form ~~/ |
| Under Colgate scoring: 14.2 pts/g   Under YinzBurgh: 12.9                       |
| Next 4 weeks: range bars   |  If added: d win +0.6 (toss-up)  |
+--------------------------------------------------------------------------------+
```

Data: `player_card` with `player_id`, `player_name`, `pos`, `team`, `owner_roster_id`, `proj_p10`, `proj_p50`, `proj_p90`, `form_last6`, `pts_per_game_league`, `delta_win_if_added`, plus `player_search(query)` returning `player_id`, `player_name`, `pos`, `team`. Interactions: `st.selectbox` with typed search over the name list (built-in filtering, no custom component). States: empty (no query), not found, no projection. Build only after E5 (it reuses `waiver_adds` and the trade evaluator).

---

## 3. Streamlit: what it does well, what it cannot

### Fits well
| Need | Component | Notes |
|---|---|---|
| Multipage | `st.navigation([st.Page(...)])` with `st.set_page_config(layout="wide")` in the entrypoint `app.py`; pages in `pages/` or defined in code | Position `"sidebar"` or `"top"`. League selector and week selector go in the entrypoint above the navigation so they persist. |
| Shared state | `st.session_state` keys `league_id`, `week`, plus per-view keys | Set defaults once in `app.py` |
| Caching | `@st.cache_data(ttl=...)` for data-layer reads, keyed by (league, week, file mtime). `@st.cache_resource` for any long-lived resource | Pass the parquet `mtime` as an argument so a refresh busts the cache. Engine output is precomputed, so reads are cheap and `ttl` is only a safety net. |
| Range bar | `st.column_config.ImageColumn` with a base64 SVG data URI | Checked in the prototype: renders in `st.dataframe`. Helper function builds the SVG from `p10, p50, p90` and the shared axis. |
| Sparkline | `st.column_config.LineChartColumn`, `BarChartColumn` | Checked. Takes a list column. |
| Progress and win% | `st.column_config.ProgressColumn(format="percent")` | Checked. Set neutral `primaryColor`. |
| Numbers | `st.column_config.NumberColumn(format="%+.1f")` for signed deltas | |
| KPI tiles | `st.metric(label, value, delta, border=True)` | `delta_color` default gives green and red, which matches the rule. `"off"` for toss-ups. |
| Row selection | `st.dataframe(on_select="rerun", selection_mode="single-row")` | For waiver detail |
| Charts | `st.line_chart`, `st.bar_chart` for first pass. Altair (bundled with Streamlit) for the histogram and for highlighting my series via a `color` condition | No new dependency |
| Layout | `st.columns`, `st.container(border=True)`, `st.tabs`, `st.expander`, `st.sidebar` | |
| Trade builder state | `st.multiselect(key=...)` plus `st.session_state` plus `st.button` | Checked with `streamlit.testing.v1.AppTest`: selecting assets, clicking Evaluate, and reading a metric works. Use `st.form` if the sim is slow, so widgets do not rerun on every change. |
| Dynamic reruns | `@st.fragment` on the trade result so the rest of the page does not rerun | |
| Dev loop | `streamlit run app.py`, hot reload on save, `AppTest` for headless smoke tests | |

### Cannot do, or does badly
- **Per-cell colors and custom HTML in a dataframe.** Only `pandas.Styler` background and text color (CSS limited). Delta chips are plain signed text with Styler green/red font color, not pills.
- **A real range-bar column.** The data-URI image is a workaround. It is not interactive (no hover tooltip with the p10 and p90 numbers). Mitigation: the numbers live in adjacent hidden-by-default columns, or in the selected-row detail.
- **Drag and drop lineups.** No built-in drag. Would need a community component (e.g. `streamlit-sortables`), which is a risk for a rough tool. Not needed: the engine recommends, the user sets it in Sleeper.
- **Runtime theme toggle.** Theme comes from config or system. The in-app switch is a hack that reloads the page. Skip it.
- **Fine layout control.** Columns are equal-ish width, no CSS grid. Rows with unequal heights misalign. A small `st.markdown(unsafe_allow_html=True)` CSS block is the escape hatch, kept small and local.
- **Full-script reruns.** Every widget touch reruns the script. Fine for read-only precomputed data, painful for anything that calls the simulator live. Rule: the UI never runs the simulator except the trade Evaluate button and optional lineup what-if, both wrapped in `st.spinner`, `st.fragment`, and a cache keyed on inputs.
- **Background work.** A long simulation run blocks the session. Long jobs run offline (CLI or launchd), the UI reads parquet.
- **Cross-page deep links with state.** `st.switch_page` plus `session_state` works but is clumsy, and `st.query_params` gives bookmarkable URLs for league and week.
- **Tooltips on cells.** Only column-level `help=`.
- **Multi-user, auth, mobile polish.** Out of scope. It does work in a phone browser on the same Wi-Fi if started with `--server.address 0.0.0.0` (do not do this without thinking: no auth).

### Signals it is time to move to React (Tremor or shadcn)
Move when two or more of these are true, not one:
1. You keep adding CSS injection to make Streamlit tables look right (the CSS block passes about 100 lines).
2. You want hover tooltips on range bars, or per-cell pills and badges, on more than one view.
3. The trade builder needs drag-and-drop, side-by-side live recalculation as you add each asset, or undo, and Evaluate-then-wait feels bad.
4. A rerun takes more than about 1 second on common interactions even with `st.fragment` and caching.
5. You want the dashboard on your phone regularly, or you want to share it with a league mate.
6. You find yourself writing a custom component for a third thing.
7. Streamlit's page structure fights the navigation you want (e.g. persistent slide-over panels, a global command palette, keyboard shortcuts).

The data layer in section 4 is the migration seam: the React app would call the same functions through a thin FastAPI wrapper that returns JSON, no engine change.

---

## 4. Data layer interface

Module `fantasy.data_api` (`src/fantasy/data_api.py`). Rules: pure read functions, no Streamlit imports, no mutation, return `polars.DataFrame` for tables or plain dataclasses/dicts for single records. The UI never touches parquet directly. Each function reads engine output (parquet) for the given `league_id` and `week`. If output is missing, return an empty frame with the correct columns (never raise for "not computed yet"). Raise only for programmer errors.

```python
# Common
def list_leagues() -> pl.DataFrame
#   league_id, league_name, scoring_label, n_teams, my_roster_id, trade_deadline_week
def current_week() -> int
def data_status() -> pl.DataFrame
#   source, last_refresh_utc, status, detail

# Home (E1 minimal, E4 and E5 fill in)
def league_summary(league_id: str, week: int) -> dict
#   win_prob, win_prob_if_act, playoff_prob, title_prob, rank_now, n_teams, record
def matchup_totals(league_id: str, week: int) -> pl.DataFrame
#   side, team_name, p10, p50, p90
def actions(league_id: str, week: int, limit: int = 3) -> pl.DataFrame
#   rank, kind, text, delta_win, delta_title, confidence, link_view
def alerts(league_id: str, week: int) -> pl.DataFrame
#   severity, kind, text, at_utc

# E1
def roster(league_id: str, roster_id: int | None = None) -> pl.DataFrame
#   player_id, player_name, pos, team, slot, injury_status
def scoring_settings(league_id: str) -> dict       # ppr, int_penalty, superflex, roster_slots, etc.

# E4
def lineup_summary(league_id: str, week: int, objective: str = "win_prob") -> dict
def lineup_slots(league_id: str, week: int, objective: str = "win_prob") -> pl.DataFrame
def bench_players(league_id: str, week: int) -> pl.DataFrame
def streaming_notes(league_id: str, week: int) -> pl.DataFrame
def lineup_explain(league_id: str, week: int) -> pl.DataFrame
def season_summary(league_id: str) -> dict
def odds_history(league_id: str) -> pl.DataFrame
def rank_distribution(league_id: str, roster_id: int | None = None) -> pl.DataFrame
def schedule_ahead(league_id: str) -> pl.DataFrame
def schedule_strength(league_id: str) -> pl.DataFrame

# E5
def waiver_adds(league_id: str, week: int, limit: int = 25) -> pl.DataFrame
def waiver_add_horizon(league_id: str, add_player_id: str) -> pl.DataFrame
def waiver_context(league_id: str) -> dict
def trending_adds(limit: int = 20) -> pl.DataFrame
def league_teams(league_id: str) -> pl.DataFrame
def trade_assets(league_id: str, roster_id: int) -> pl.DataFrame
def evaluate_trade(league_id: str, give_ids: list[str], get_ids: list[str],
                   partner_roster_id: int) -> pl.DataFrame   # two rows, side me/them
def trade_ideas(league_id: str, limit: int = 10) -> pl.DataFrame   # optional

# Players (after E5)
def player_search(query: str, limit: int = 15) -> pl.DataFrame
def player_card(league_id: str, player_id: str, week: int) -> dict
```

Contracts:
- `confidence` is one of `clear`, `lean`, `toss-up`, computed in the engine (not the UI) from `sim_share_better` so React gets the same label.
- All probabilities are floats in 0 to 1. UI formats them. All deltas are in probability points as floats (0.041 = 4.1 points), UI formats.
- `p10 <= p50 <= p90` always. A test enforces it.
- Every frame carries `league_id` and, where relevant, `week`, and a `computed_at_utc` column so the UI can show staleness without a second call.
- `evaluate_trade` is the only function that may run the simulator. Everything else reads precomputed output. It caches by (league, sorted give, sorted get, partner, `rosters_hash`).
- Types: Polars in, Polars out. The Streamlit side calls `.to_pandas()` only at the `st.dataframe` boundary (pandas needed for `Styler`).
- A `fake_data.py` module provides the same functions backed by synthetic data so the UI can be built and tested before the engine exists. This is the one piece of scaffolding worth building first (story D1).

---

## 5. Story list (superseded)

The canonical story list is docs/backlog.md. The original draft below keeps each D story's done-when wording for reference. It still mentions a fake data layer, page smoke tests, a lineup what-if and a market-value comparison, all of which were dropped.

### E1 (Sleeper sync, dashboard shell)
- **D1. Shell and fake data layer.** Streamlit app with `st.navigation`, league and week selectors in `session_state`, neutral theme in `.streamlit/config.toml`, `app/data.py` signature stubs, and `fake_data.py` backing them. Done when: all five views open and show a title and "as of" line with fake data in light and dark mode.
- **D2. Range-bar and delta helpers.** `ui/widgets.py` with `range_bar_uri(p10, p50, p90, axis)`, signed-delta formatter, confidence label formatter, and a unit test for each (including `p10 <= p50 <= p90`). Done when: a demo table with range bar, sparkline, and progress columns renders correctly in both themes.
- **D3. Roster and scoring panel (real data).** `roster()` and `scoring_settings()` read from the synced store; Home shows a per-league card with record, scoring labels, and roster. Done when: both leagues show rosters and correct scoring settings (the E1 done-when).
- **D4. Freshness, stale, and error states.** `data_status()` wired to a footer line and an amber banner on stale or failed sources, plus the "Run sync" empty state. Done when: deleting a parquet file shows the empty-state message instead of a traceback.
- **D5 (optional). Page smoke tests.** `streamlit.testing.v1.AppTest` test that loads each page with fake data and asserts no exception. Done when: `uv run pytest` runs five page tests green.

### E4 (simulation and lineup optimizer)
- **D6. Lineup view on real output.** Slot table with projection, range bar, opponent, injury badge, and the swap highlight. Done when: Lineup for both leagues matches the optimizer's output frame row for row.
- **D7. Objective toggle and header deltas.** Win-prob versus points radio, current versus recommended win%, confidence tag. Done when: flipping the toggle changes the recommended lineup and header numbers with no recompute.
- **D8. Home cards with team-total range bars and actions.** `league_summary`, `matchup_totals`, `actions` (lineup actions only at this point). Done when: Home shows win%, two range bars on a shared axis, and the top lineup action per league.
- **D9. K and DEF streaming note and lock state.** `streaming_notes` text row, greyed locked players using `kickoff_utc`. Done when: a player whose game has started is greyed and not recommended.
- **D10. Outlook panel.** Title odds line, rank histogram, schedule table, SOS, with `odds_history` snapshotting wired in the weekly job. Done when: Outlook shows both charts and the schedule for either league; the line shows a single point on first run with the "appears next week" note.
- **D11 (optional). Lineup what-if.** "Force start" column, call to `lineup_whatif`. Done when: forcing a player updates the win% in under 3 seconds. Cut if the optimizer cannot meet that.

### E5 (waivers and trades)
- **D12. Waivers table and detail strip.** `waiver_adds` with drop suggestion, delta columns, row selection, 4-week range strip. Done when: selecting a row shows that player's next-4-weeks medians and bye week.
- **D13. Waiver context and trending.** Priority, next run time, claim-order text, Sleeper trending expander. Done when: the claim-order tip names the add and the fallback.
- **D14. Trade builder.** Partner select, two multiselects with `session_state`, Evaluate button, cache by input hash. Done when: choosing assets and clicking Evaluate shows my and their before/after odds, and re-evaluating the same trade is instant.
- **D15. Trade result panel and warnings.** Both sides, market value comparison, `roster_warnings`, deadline disable. Done when: an invalid roster-size trade shows an amber warning, and Evaluate is disabled after the deadline.
- **D16. Home actions across kinds.** `actions` merges lineup, waiver, and trade items ranked by `delta_win`. Done when: Home shows the top 3 mixed actions per league and each click lands on the correct view with the item preselected.
- **D17 (optional). Players search.** `player_search`, `player_card`. Done when: searching a name shows projection range, owner, and the add or trade delta.
- **D18 (optional). Partner finder.** `trade_ideas` list. Done when: the list shows at least one mutually positive trade or a "none found" message. Only after D14 and D15 are solid.

---

## 6. Does not make sense or is over-built

Direct list, against the current UI plan in `one-pager.md`.

1. **The "both leagues" option in the league switch.** For Home it is the right default (the cards sit side by side). For Lineup, Waivers, Trades, Outlook it makes no sense: different scoring, different rosters, different opponents. A "both" toggle on those views would be a merged table of unlike things. Fix: Home shows both, everything else is single-league. The selector has two values, not three.
2. **Dark mode toggle.** Streamlit cannot do it cleanly at runtime. Follow the system theme. Spend no time here.
3. **Lock alerts as a feature.** Sleeper gives no lock or deadline signal as such, but kickoff times from the nflverse schedule are enough to grey locked players and show "first kickoff Thu 8:15 PM". That is cheap and enough. A live countdown or push alert is over-built for a tool opened a few times a week, and Streamlit cannot push notifications anyway.
4. **Injury alerts as live status.** nflverse injury reports update on a weekly (and sometimes daily) cadence. Do not promise real-time. Show `injury_status` and its `as_of` date. Late-breaking inactives on Sunday morning will not be there unless Sleeper's player file (once-a-day) carries them. State this limit in the UI footer.
5. **Title odds over time and the rank histogram on day one.** Over time needs a snapshot of the odds every week, which does not exist before the pipeline writes it. Build snapshotting in E4, ship the chart when there are two or more points. The histogram is fine from the first run.
6. **Schedule strength as a separate chart.** One number (SOS rank) plus the schedule table is enough. A SOS chart is redundant with the per-week win probability in `schedule_ahead`.
7. **Partner finder.** It needs a simulation per candidate pair across every roster in the league (10 teams, many asset combinations). It is the heaviest piece in the UI plan and it is not needed to use the trade builder. Mark optional (D18), after the deadline pressure is gone or if evaluation is fast.
8. **A larger "what-if" lineup editor and drag-and-drop.** Sleeper is read-only, so you set the lineup in Sleeper anyway. Dragging in the dashboard would not change the real lineup. Only the optional "Force start" checkbox is justified.
9. **Range bars everywhere.** Range bars on every table (waivers, trade assets, search) make screens noisy and slow to build (image data URIs per row). Use them on Home team totals, the Lineup slot table, and the waiver detail. Use plain p50 plus a tooltip-free text range (`11 (4 to 22)`) elsewhere.
10. **Streamlit sparklines as "form" on every row.** Fine on Lineup. On Waivers and Players it duplicates the horizon strip. Keep it to one place per view.
11. **Real-time recompute in the UI.** Anything that implies the UI runs the simulator on a widget change (live win% as you tick assets in the trade builder, for example) is infeasible at Streamlit's rerun-the-script model with seconds-long simulations. Evaluate is an explicit button. If the user wants live, that is a React-move signal, and it also needs a faster trade simulator, not just a new front end.
12. **Copy-the-best-tools framing for the UI.** Few fantasy tools show uncertainty ranges at all. Matching "what the best public tools do" on UI means a table with a projection and a start/sit tag. The range bar and the confidence tag are the actual differentiators, so those two are where effort goes. Everything else (league page look, team logos, player headshots, animations) is polish that can wait for the E7 "polished UI" epic.
13. **Per-view "Both" scoring toggles on projections.** Players search shows both scoring systems in one line, which is fine and useful. Nothing beyond that.
14. **Hover tooltips on range bars.** Infeasible with the image-column approach. Replace with numbers in the row and the detail strip. If tooltips matter, that is a React-move signal.
15. **Separate "Alerts" panel on Home with many alert kinds.** Keep to injury on a started or likely-start player, the next waiver run, and stale data. Everything else is noise.

---

## 7. Prototype record (not in the repo)

Throwaway app at `/private/tmp/claude-501/-Users-eliheakins/f1c4f309-1847-4dfc-9529-f4531042b485/scratchpad/dashboard/app.py`, fake data, Streamlit 1.66.1 via `uv run --with streamlit`.
- Range-bar column via `ImageColumn` with a base64 SVG: renders correctly, checked by screenshot. Median tick and shared-axis bars read well. Dark-mode legibility was not tested.
- `LineChartColumn` and `ProgressColumn`: render, but pick up the theme primary color (red by default).
- Trade builder: two `multiselect`s with `session_state` plus an Evaluate button, driven headless by `AppTest`: state persisted, the metric showed `11.2%` with delta `+1.4%`.
- Not tested: dark mode, `st.navigation` with several pages, `st.fragment` behavior under a slow simulation, a real engine call, and `on_select` row selection.
