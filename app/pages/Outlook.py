import polars as pl
import streamlit as st
from ui import league_picker, no_data_warning

from fantasy import data_api

league_key, _week = league_picker()
st.title("Outlook")
odds = data_api.season_odds(league_key)
if odds.is_empty():
    no_data_warning()
    st.stop()

st.caption(
    "Simulated rest of season, 20,000 runs, assuming current rosters: no waiver moves, trades or "
    "new injuries beyond the usual spread of game outcomes. Defenses are a league average for now."
)
st.dataframe(
    odds.select("team_name", "p_playoffs", "p_bye", "p_title", "exp_wins", "is_me"),
    hide_index=True,
    width="stretch",
    column_config={
        "team_name": "Team",
        "p_playoffs": st.column_config.ProgressColumn(
            "Playoffs", format="percent", min_value=0.0, max_value=1.0
        ),
        "p_bye": st.column_config.NumberColumn("Bye", format="percent"),
        "p_title": st.column_config.NumberColumn("Title", format="percent"),
        "exp_wins": st.column_config.NumberColumn("Exp. wins", format="%.1f"),
        "is_me": "You",
    },
)

history = data_api.odds_history(league_key)
mine = odds.filter(pl.col("is_me"))
if not mine.is_empty() and history["run_at"].n_unique() >= 2:
    mine_history = history.filter(pl.col("roster_id") == mine["roster_id"][0]).sort("run_at")
    st.subheader("Your odds over saved runs")
    st.line_chart(mine_history, x="run_at", y=["p_playoffs", "p_title"])
else:
    st.caption("The odds-over-time chart appears after the simulation has run at least twice.")
