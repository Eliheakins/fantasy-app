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

try:
    seeds = data_api.seed_distribution(league_key)
    games = data_api.schedule(league_key)
except FileNotFoundError:
    seeds, games = pl.DataFrame(), pl.DataFrame()
if not seeds.is_empty():
    st.subheader("Where you finish")
    st.caption(
        "Chance of each regular-season seed. Seeds 1 to 6 make the playoffs, 1 and 2 get byes."
    )
    st.bar_chart(seeds.with_columns(pl.col("seed").cast(pl.String)), x="seed", y="p")
if not games.is_empty():
    st.subheader("Your remaining schedule")
    st.caption(
        "Expected points are each team's best lineup this week, with K and DEF at league "
        "averages. The win chance is a quick normal approximation, not the full simulation."
    )
    st.dataframe(
        games,
        hide_index=True,
        width="stretch",
        column_config={
            "week": "Week",
            "opponent": "Opponent",
            "my_points": st.column_config.NumberColumn("You", format="%.1f"),
            "their_points": st.column_config.NumberColumn("Them", format="%.1f"),
            "win_chance": st.column_config.ProgressColumn(
                "Win chance", format="percent", min_value=0.0, max_value=1.0
            ),
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
