"""Which leagues an account may see, and which team in each is theirs.

A league is visible to an account when the account added it (a row in account_leagues), or, for the
admin, when it is one of the leagues in config.toml. Nobody sees another account's league, the
admin included. The team an account views by default is the roster its Sleeper user id owns; the
owner's own leagues keep using Sleeper's is_me marker, as they always have.
"""

import re
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy.auth import accounts
from fantasy.config import load_config

LEAGUE_PATH = re.compile(r"^/api/leagues/([^/]+)")


def league_ids(account: dict[str, Any], data_dir: Path | None = None) -> set[str]:
    with accounts.open_db(data_dir) as conn:
        ids = accounts.granted_league_ids(conn, account["id"])
    if account["is_admin"]:
        ids |= set(load_config().leagues.values())
    return ids


def league_id_for(league_key: str, data_dir: Path | None = None) -> str | None:
    try:
        table = store.read_table("leagues", "raw", data_dir)
    except FileNotFoundError:
        return None
    match = table.filter(pl.col("league_key") == league_key)
    return str(match["league_id"][0]) if not match.is_empty() else None


def can_see(account: dict[str, Any], league_key: str, data_dir: Path | None = None) -> bool:
    league_id = league_id_for(league_key, data_dir)
    return league_id is not None and league_id in league_ids(account, data_dir)


def default_team(
    account: dict[str, Any] | None, league_key: str | None, data_dir: Path | None = None
) -> int | None:
    """The roster this account views by default, or None to keep Sleeper's is_me team."""
    if account is None or league_key is None or not account["sleeper_user_id"]:
        return None
    league_id = league_id_for(league_key, data_dir)
    if league_id is None:
        return None
    teams = store.read_table("league_teams", "raw", data_dir).filter(
        pl.col("league_id") == league_id
    )
    if teams["is_me"].any():  # the owner's league: is_me already says which team is theirs
        return None
    mine = teams.filter(pl.col("owner_id") == account["sleeper_user_id"])
    return int(mine["roster_id"][0]) if not mine.is_empty() else None


def only_visible(
    frame: pl.DataFrame, account: dict[str, Any] | None, data_dir: Path | None = None
) -> pl.DataFrame:
    """`frame` (it has a league_id column) cut down to the account's leagues; all of it with no
    account, which is a local run with login off."""
    if account is None:
        return frame
    return frame.filter(pl.col("league_id").is_in(sorted(league_ids(account, data_dir))))


TEAM_COLUMNS = ("roster_id", "team_name", "wins", "losses", "ties", "points_for")


def with_account_team(
    frame: pl.DataFrame, account: dict[str, Any] | None, data_dir: Path | None = None
) -> pl.DataFrame:
    """Fill the team columns of `frame` (one row per league) with the account's own roster where
    the league has no is_me team, so a friend's league shows the friend's record."""
    if account is None or not account["sleeper_user_id"]:
        return frame
    mine = (
        store.read_table("league_teams", "raw", data_dir)
        .filter(pl.col("owner_id") == account["sleeper_user_id"])
        .select("league_id", *TEAM_COLUMNS)
        .rename({c: f"{c}_mine" for c in TEAM_COLUMNS})
    )
    joined = frame.join(mine, on="league_id", how="left")
    return joined.with_columns(
        [pl.coalesce(pl.col(c), pl.col(f"{c}_mine")).alias(c) for c in TEAM_COLUMNS]
    ).drop([f"{c}_mine" for c in TEAM_COLUMNS])
