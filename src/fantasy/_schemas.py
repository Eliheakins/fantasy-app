"""Column schemas shared by the data_api modules."""

import polars as pl

_S, _F, _B, _I = pl.String, pl.Float64, pl.Boolean, pl.Int64
# Output schemas for the engine frames: an empty result keeps its columns.
ENGINE_SCHEMAS: dict[str, dict[str, pl.DataType | type[pl.DataType]]] = {
    "lineup": {
        "slot": _S,
        "gsis_id": _S,
        "full_name": _S,
        "position": _S,
        "projection": _F,
        "p10": _F,
        "p90": _F,
        "starting_now": _B,
        "recommended": _B,
        "injury": _S,
        "injury_note": _S,
        "locked": _B,
        "actual": _F,
        "game": _S,
    },
    "win_probability": {
        "option": _S,
        "win_prob": _F,
        "expected_points": _F,
        "gsis_ids": pl.List(_S),
        "slots": pl.List(_S),
        "share_better": _F,
        "tag": _S,
        "floor": _F,
        "median": _F,
        "ceiling": _F,
        "opp_floor": _F,
        "opp_median": _F,
        "opp_ceiling": _F,
        "script": _S,
    },
    "streamers": {
        "unit": _S,
        "name": _S,
        "team": _S,
        "is_mine": _B,
        "this_week": _F,
        "next_three": _F,
    },
    "waivers": {
        "gsis_id": _S,
        "full_name": _S,
        "position": _S,
        "drop_name": _S,
        "delta_points": _F,
        "playoff_delta": _F,
        "title_delta": _F,
        "se_title": _F,
        "trending_adds": pl.Int64,
    },
    "season_odds": {
        "roster_id": pl.Int64,
        "team_name": _S,
        "p_playoffs": _F,
        "p_bye": _F,
        "p_title": _F,
        "exp_wins": _F,
        "is_me": _B,
    },
    # rank 1 is the highest expected score this week; sos_rank 1 is the toughest remaining schedule
    "power_rankings": {
        "roster_id": _I,
        "team_name": _S,
        "is_me": _B,
        "rank": _I,
        "exp_points_week": _F,
        "exp_wins": _F,
        "p_playoffs": _F,
        "p_title": _F,
        "sos_remaining": _F,
        "sos_rank": _I,
    },
    # one row per team and position (QB, RB, WR, TE) plus "overall"; rank 1 is strongest and
    # the grade is by rank scaled to the league size (top fifth A ... bottom fifth F). vor_per_week
    # is the starters' value over stand-ins, depth_per_week the bench's; score blends them 75/25
    "team_grades": {
        "roster_id": _I,
        "team_name": _S,
        "is_me": _B,
        "position": _S,
        "vor_per_week": _F,
        "depth_per_week": _F,
        "score": _F,
        "rank": _I,
        "grade": _S,
    },
    # ap_* is the all-play record; exp_wins = all-play win share * weeks; luck = wins - exp_wins
    "luck": {
        "roster_id": _I,
        "team_name": _S,
        "is_me": _B,
        "weeks": _I,
        "wins": _I,
        "losses": _I,
        "ties": _I,
        "ap_wins": _I,
        "ap_losses": _I,
        "ap_ties": _I,
        "exp_wins": _F,
        "luck": _F,
    },
    "manager_grades": {
        "roster_id": _I,
        "team_name": _S,
        "is_me": _B,
        "weeks": _I,
        "actual_points": _F,
        "optimal_points": _F,
        "efficiency": _F,
        "bench_points_left": _F,
    },
    # d_* is my change in odds if this side wins, against the plain odds
    "what_if": {
        "winner_id": _I,
        "loser_id": _I,
        "winner": _S,
        "loser": _S,
        "involves_me": _B,
        "p_condition": _F,
        "n_runs": _I,
        "d_playoffs": _F,
        "d_title": _F,
    },
}

_SIDE_COLUMNS: dict[str, pl.DataType | type[pl.DataType]] = {
    "roster_id": pl.Int64,
    "team_name": _S,
    "is_me": _B,
    "projected": _F,  # expected points to the end of the week
    "floor": _F,
    "median": _F,
    "ceiling": _F,
    "win_prob": _F,
    "points": _F,  # already scored
    "share_left": _F,  # share of the team's starters' games still to play
}
# One row per matchup: week, matchup_id, status, then every side column for a_ and for b_.
ENGINE_SCHEMAS["scoreboard"] = {
    "week": pl.Int64,
    "matchup_id": pl.Int64,
    "status": _S,
    **{f"{side}_{name}": kind for side in ("a", "b") for name, kind in _SIDE_COLUMNS.items()},
}

OUTLOOK_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "gsis_id": _S,
    "full_name": _S,
    "position": _S,
    "owner": _S,
    "recent_ppg": _F,
    "expected_ppg": _F,
    "next_ppg": _F,
    "change": _F,
    "chance_to_play": _F,
    "label": _S,
    "why": _S,
}
