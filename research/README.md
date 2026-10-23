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
| `slot_test.py` | Does a slot corner being out help slot receivers? | Not measurable with free data (no alignment) |
| `h2h_test.py` | Does history against a specific opponent predict points, divisional or not? | No out-of-sample signal |
| `inj_explore.py` | How do injury status, practice report and injury type predict playing? | Became `stages/injuries.py` |
| `sleeper_proj.py` | How do Sleeper's projections compare with ours? | Not clean: the endpoint re-stamps after games (issue #40 reruns it on clean snapshots) |

Left out on purpose: seven exploratory scripts that only inspected data shapes (participation
files, snap-count joins, rosters).
