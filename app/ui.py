"""Shared sidebar and empty-state helpers for the dashboard pages."""

import streamlit as st

from fantasy import data_api

MAX_WEEK = 18


def no_data_warning() -> None:
    st.warning("No data yet. Run `make refresh`, then reload this page.")


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


def coming_soon(title: str, story: str, blurb: str) -> None:
    league_key, week = league_picker()
    st.title(title)
    st.caption(f"{league_key} · week {week}")
    st.info(f"{blurb} Built in {story}.")
