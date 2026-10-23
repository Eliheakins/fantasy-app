"""Shared sidebar and empty-state helpers for the dashboard pages."""

import streamlit as st

from fantasy import data_api

MAX_WEEK = 18


def no_data_warning() -> None:
    st.warning("No data yet. Run `make refresh`, then reload this page.")


STALE_HOURS = {"Sleeper": 24.0, "NFL stats": 48.0}  # past this age a banner asks for a refresh


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


def footer() -> None:
    """Sidebar line per data source with its age, and the attribution Sleeper asks for."""
    ages = data_api.freshness()
    for r in ages.iter_rows(named=True):
        st.sidebar.caption(f"{r['source']}: {r['age_hours']:.1f} hours ago")
    st.sidebar.caption("Data from Sleeper and nflverse.")


def league_picker() -> tuple[str, int]:
    """Sidebar league and week selectors. Returns (league_key, week)."""
    leagues = data_api.leagues()
    if leagues.is_empty():
        no_data_warning()
        st.stop()
    names = dict(zip(leagues["league_key"], leagues["name"], strict=True))
    league_key = st.sidebar.radio("League", list(names), format_func=names.get, key="league_key")
    current = int(leagues.filter(leagues["league_key"] == league_key)["current_week"][0] or 1)
    week = st.sidebar.selectbox("Week", range(1, MAX_WEEK + 1), index=current - 1, key="week")
    return str(league_key), int(week)
