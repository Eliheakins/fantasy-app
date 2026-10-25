"""Page logic the Streamlit pages compute themselves, lifted out so the API can serve it.

Pure functions over the frames `data_api` returns (nothing here mutates its inputs). Probabilities
stay 0 to 1; scaling to percent is a display concern.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from fantasy import store

OBJECTIVES = {
    "expected_points": "max_points",
    "win_probability": "win_prob",
    "max_ceiling": "ceiling",
    "max_floor": "floor",
}
OBJECTIVE_LABELS = {
    "expected_points": "Expected points",
    "win_probability": "Win probability",
    "max_ceiling": "Max ceiling",
    "max_floor": "Max floor",
}
NO_SWAP = "same as max points"
MIN_HISTORY_RUNS = 2
ROSTER_MOVES_WARNING = "Automatic roster moves to keep sizes equal:"


@dataclass(frozen=True)
class SwapNote:
    differs: bool
    players_in: list[str]
    players_out: list[str]
    text: str | None


@dataclass(frozen=True)
class LineupSummary:
    objective: str
    shown_points: float
    sleeper_points: float | None
    gap: float | None  # sleeper minus shown, as the page shows it
    win_prob: float | None


def record_string(wins: int | None, losses: int | None, ties: int | None) -> str:
    if wins is None or losses is None:
        return "no record yet"
    return f"{wins}-{losses}" + (f"-{ties}" if ties else "")


def _option(odds: pl.DataFrame, option: str) -> dict | None:
    if odds.is_empty():
        return None
    rows = odds.filter(pl.col("option") == option)
    return None if rows.is_empty() else rows.row(0, named=True)


def reslot(rows: pl.DataFrame, odds: pl.DataFrame, objective: str) -> pl.DataFrame:
    """Lineup rows with slot and recommended set for the option the objective picks. Expected
    points (and a missing option) leave the rows as `lineup` returned them."""
    if objective not in OBJECTIVES:
        raise ValueError(f"unknown objective {objective!r}; use one of {sorted(OBJECTIVES)}")
    option = _option(odds, OBJECTIVES[objective])
    if option is None or OBJECTIVES[objective] == "max_points":
        return rows
    slot_of = dict(zip(option["gsis_ids"], option["slots"], strict=True))
    return rows.with_columns(
        pl.col("gsis_id").is_in(list(slot_of)).alias("recommended"),
        pl.col("gsis_id").replace_strict(slot_of, default="BN").alias("slot"),
    )


def lineup_changes(rows: pl.DataFrame) -> pl.DataFrame:
    """Adds `change`: Start or Sit against the lineup set in Sleeper (blank if not known)."""
    known = pl.lit(bool(rows["starting_now"].any()))
    start = known & pl.col("recommended") & ~pl.col("starting_now")
    sit = known & pl.col("starting_now") & ~pl.col("recommended")
    return rows.with_columns(
        pl.when(start)
        .then(pl.lit("Start"))
        .when(sit)
        .then(pl.lit("Sit"))
        .otherwise(pl.lit(""))
        .alias("change")
    )


def swap_note(rows: pl.DataFrame, odds: pl.DataFrame) -> SwapNote | None:
    """Who the win-probability pick starts and sits against the max-points lineup."""
    pick, best = _option(odds, "win_prob"), _option(odds, "max_points")
    if pick is None or best is None:
        return None
    if pick["tag"] == NO_SWAP:
        return SwapNote(False, [], [], None)
    name_of = dict(zip(rows["gsis_id"], rows["full_name"], strict=True))
    ins = [name_of[i] for i in sorted(set(pick["gsis_ids"]) - set(best["gsis_ids"]))]
    out = [name_of[i] for i in sorted(set(best["gsis_ids"]) - set(pick["gsis_ids"]))]
    text = (
        f"{pick['tag'].capitalize()}: start {', '.join(ins)} over {', '.join(out)} "
        f"({pick['win_prob']:.1%} vs {best['win_prob']:.1%}). In games where the two "
        f"lineups disagree, this one wins {pick['share_better']:.0%} of the time."
    )
    return SwapNote(True, ins, out, text)


def comparison(odds: pl.DataFrame) -> pl.DataFrame:
    """One row per lineup option (not the Sleeper one), labelled, with expected points."""
    by_option = {v: OBJECTIVE_LABELS[k] for k, v in OBJECTIVES.items()}
    return (
        odds.filter(pl.col("option") != "sleeper_now")
        .with_columns(pl.col("option").replace_strict(by_option, default=pl.col("option")))
        .select("option", "win_prob", "expected_points", "floor", "median", "ceiling")
    )


def lineup_summary(rows: pl.DataFrame, odds: pl.DataFrame, objective: str) -> LineupSummary:
    shown = reslot(rows, odds, objective)
    shown_points = float(shown.filter(pl.col("recommended"))["projection"].sum())
    known = bool(shown["starting_now"].any())
    now = float(shown.filter(pl.col("starting_now"))["projection"].sum()) if known else None
    option = _option(odds, OBJECTIVES[objective])
    return LineupSummary(
        objective,
        shown_points,
        now,
        None if now is None else now - shown_points,
        None if option is None else float(option["win_prob"]),
    )


def asset_labels(assets: pl.DataFrame) -> dict[str, str]:
    return {
        r["gsis_id"]: f"{r['full_name']} ({r['position']}, {r['ros_points']:.0f} pts)"
        for r in assets.iter_rows(named=True)
    }


def roster_moves_warning(changes: pl.DataFrame) -> str | None:
    return None if changes.is_empty() else ROSTER_MOVES_WARNING


def unmatched_names(unmatched: pl.DataFrame) -> list[str]:
    return [
        f"{r['full_name']} ({r['position']}, {r['team']})" for r in unmatched.iter_rows(named=True)
    ]


def my_odds_history(history: pl.DataFrame, odds: pl.DataFrame) -> pl.DataFrame:
    """My team's saved runs, oldest first; empty until the simulation has run twice."""
    mine = odds.filter(pl.col("is_me"))
    if mine.is_empty() or history["run_at"].n_unique() < MIN_HISTORY_RUNS:
        return history.clear()
    return history.filter(pl.col("roster_id") == mine["roster_id"][0]).sort("run_at")


def trade_deadline(league_key: str, data_dir: Path) -> int | None:
    """Last week trades are allowed, or None if the league has no deadline set."""
    rows = store.read_table("leagues", "raw", data_dir).filter(pl.col("league_key") == league_key)
    if rows.is_empty() or rows["trade_deadline"][0] is None:
        return None
    return int(rows["trade_deadline"][0])


_POINTS_IN_TEXT = re.compile(r"([+-]\d+(?:\.\d+)?) points")


def action_fields(actions: pl.DataFrame, odds: pl.DataFrame | None) -> list[dict[str, object]]:
    """Action rows plus delta_points (parsed from the text's "+N points", else None) and
    share_better (the win_prob option's, only on the Win probability action)."""
    share = None
    if odds is not None and not odds.is_empty():
        share = odds.filter(pl.col("option") == "win_prob")["share_better"][0]
    out = []
    for r in actions.iter_rows(named=True):
        m = _POINTS_IN_TEXT.search(r["text"])
        out.append(
            {
                **r,
                "delta_points": float(m[1]) if m else None,
                "share_better": share if r["kind"] == "Win probability" else None,
            }
        )
    return out


def scoreboard_rows(frame: pl.DataFrame) -> list[dict[str, object]]:
    """Each flat `a_*` / `b_*` row as {week, matchup_id, status, a: {...}, b: {...}}."""
    out = []
    for r in frame.to_dicts():
        sides = {s: {k[2:]: v for k, v in r.items() if k.startswith(f"{s}_")} for s in ("a", "b")}
        head = {k: r[k] for k in ("week", "matchup_id", "status")}
        out.append({**head, **sides})
    return out
