"""Shared sidebar and empty-state helpers for the dashboard pages."""

import polars as pl
import streamlit as st

from fantasy import data_api

MAX_WEEK = 18
CACHE_SECONDS = 300


cached = st.cache_data(ttl=CACHE_SECONDS)
# one-line bindings: the pages call these, so every page shares one cache entry per league
season_odds = cached(data_api.season_odds)
seed_distribution = cached(data_api.seed_distribution)
schedule = cached(data_api.schedule)
odds_history = cached(data_api.odds_history)
waivers = cached(data_api.waivers)
position_strength = cached(data_api.position_strength)
player_weeks = cached(data_api.player_weeks)
streamers = cached(data_api.streamers)
player_outlook = cached(data_api.player_outlook)
find_trades = cached(data_api.find_trades)
trade_partners = cached(data_api.trade_partners)
trade_assets = cached(data_api.trade_assets)


@st.cache_data(ttl=CACHE_SECONDS)
def cached_win_probability(league_key: str, week: int = 0) -> pl.DataFrame:
    """Shared by Home and Lineup so the simulation runs once per league and week."""
    return data_api.win_probability(league_key, week)


@st.cache_data(ttl=CACHE_SECONDS)
def cached_lineup(league_key: str, week: int = 0) -> pl.DataFrame:
    return data_api.lineup(league_key, week)


def no_data_warning() -> None:
    st.warning("No data yet. Run `make refresh`, then reload this page.")


def strength_table(league_key: str) -> None:
    """My value over replacement by position, with the league rank."""
    st.dataframe(
        position_strength(league_key),
        hide_index=True,
        width="stretch",
        column_config={
            "position": "Position",
            "vor_per_week": st.column_config.NumberColumn(
                "Points a week over replacement", format="%.1f"
            ),
            "rank": "League rank",
            "teams": "Teams",
        },
    )


STALE_HOURS = {
    "Sleeper": 24.0,
    "NFL stats": 48.0,
    "Simulation": 48.0,
}  # past this age a banner asks for a refresh


def stale_banner() -> None:
    """Amber banner when Sleeper or NFL data is older than its limit."""
    ages = data_api.freshness()
    old = [
        f"{r['source']} ({r['age_hours']:.0f} hours old)"
        for r in ages.iter_rows(named=True)
        if r["age_hours"] > STALE_HOURS.get(r["source"], float("inf"))
    ]
    if old:
        st.warning(f"Stale data: {', '.join(old)}. Run `make refresh`.")
    missing = data_api.missing_layers()
    if missing:
        st.warning(f"Running without: {', '.join(missing)}. Run `make refresh`.")
    behind = data_api.simulation_behind_inputs()
    if behind:
        st.warning(f"{behind}. Run `make refresh`.")


def footer() -> None:
    """Sidebar line per data source with its age, and the attribution Sleeper asks for."""
    ages = data_api.freshness()
    for r in ages.iter_rows(named=True):
        st.sidebar.caption(f"{r['source']}: {r['age_hours']:.1f} hours ago")
    st.sidebar.caption("Data from Sleeper and nflverse.")


def league_picker(show_week: bool = True) -> tuple[str, int]:
    """Sidebar league and week selectors. Returns (league_key, week); pages that ignore the week
    pass show_week=False, and get the league's current week back."""
    leagues = data_api.leagues()
    if leagues.is_empty():
        no_data_warning()
        st.stop()
    names = dict(zip(leagues["league_key"], leagues["name"], strict=True))
    league_key = st.sidebar.radio("League", list(names), format_func=names.get, key="league_key")
    current_week = leagues.filter(leagues["league_key"] == league_key)["current_week"][0]
    if current_week is None:
        st.sidebar.warning("Current week unknown; showing week 1. Run `make refresh`.")
    current = int(current_week or 1)
    if not show_week:
        return str(league_key), current
    week = st.sidebar.selectbox("Week", range(1, MAX_WEEK + 1), index=current - 1, key="week")
    return str(league_key), int(week)
