"""Column schemas shared by the data_api modules."""

import polars as pl

_S, _F, _B = pl.String, pl.Float64, pl.Boolean
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
