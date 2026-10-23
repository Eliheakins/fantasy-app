"""Dashboard entry point. Run: make app"""

import polars as pl
import streamlit as st
from ui import league_picker, no_data_warning

from fantasy import data_api

st.set_page_config(page_title="Fantasy", layout="wide")


def home() -> None:
    league_key, _week = league_picker()
    st.title("Home")
    leagues = data_api.leagues()
    if leagues.is_empty():
        no_data_warning()
        return
    for row in leagues.to_dicts():
        if row["league_key"] != league_key:
            continue
        record = f"{row['wins']}-{row['losses']}" + (f"-{row['ties']}" if row["ties"] else "")
        st.subheader(f"{row['name']} · {row['team_name']}")
        st.caption(f"{record} · {row['points_for']:.1f} PF · week {row['current_week']}")
        st.caption(row["scoring_labels"])
        mine = data_api.season_odds(league_key).filter(pl.col("is_me"))
        if not mine.is_empty():
            odds = mine.row(0, named=True)
            cols = st.columns(4)
            cols[0].metric("Make playoffs", f"{odds['p_playoffs']:.0%}")
            cols[1].metric("First-round bye", f"{odds['p_bye']:.0%}")
            cols[2].metric("Win the title", f"{odds['p_title']:.1%}")
            cols[3].metric("Expected wins", f"{odds['exp_wins']:.1f}")
            st.caption("Odds assume current rosters. Details on the Outlook page.")
        roster = data_api.roster(league_key)
        st.dataframe(
            roster.select("full_name", "position", "team", "injury_status", "is_starter"),
            hide_index=True,
            column_config={
                "full_name": "Player",
                "position": "Pos",
                "team": "Team",
                "injury_status": "Injury",
                "is_starter": "Starting",
            },
            width="stretch",
        )
        unmatched = data_api.unmatched()
        if not unmatched.is_empty():
            st.caption(f"{unmatched.height} active players have no nflverse history yet.")


pages = [
    st.Page(home, title="Home", default=True),
    st.Page("pages/Lineup.py", title="Lineup"),
    st.Page("pages/Waivers.py", title="Waivers"),
    st.Page("pages/Trades.py", title="Trades"),
    st.Page("pages/Outlook.py", title="Outlook"),
]
st.navigation(pages).run()
