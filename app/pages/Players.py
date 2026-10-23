import streamlit as st
from ui import league_picker, no_data_warning

from fantasy import data_api

league_key, _week = league_picker()
st.title("Player outlook")
scope = st.radio(
    "Players", ["My roster", "Other rosters", "Free agents"], horizontal=True, key="outlook_scope"
)
key = {"My roster": "mine", "Other rosters": "league", "Free agents": "free"}[scope]


@st.cache_data(ttl=300)
def load(league: str, which: str):
    return data_api.player_outlook(league, which)


try:
    table = load(league_key, key)
except FileNotFoundError:
    no_data_warning()
    st.stop()

if table.is_empty():
    st.info("No players to show.")
    st.stop()

st.caption(
    "Change is the projected points a game over the next four games (when he plays) minus his "
    "last four games. A player is Improving or Regressing past 1.5 points a game. Three drivers "
    "are modeled because they held up in tests on 2019 to 2025: players back from missed games "
    "play below projection for a game or two (a player who missed games with no injury report "
    "much more), receivers and backs gain when teammates who carry targets or carries are out, "
    "and points above or below what usage is worth tend to be partly luck. Usage trends, "
    "schedule strength and rookie status added nothing on top of the projection, so they are "
    "not used."
)
st.dataframe(
    table.select(
        "full_name",
        "position",
        "owner",
        "label",
        "recent_ppg",
        "expected_ppg",
        "next_ppg",
        "change",
        "chance_to_play",
        "why",
    ),
    hide_index=True,
    width="stretch",
    column_config={
        "full_name": "Player",
        "position": "Pos",
        "owner": "Owner",
        "label": "Outlook",
        "recent_ppg": st.column_config.NumberColumn("Last 4 games", format="%.1f"),
        "expected_ppg": st.column_config.NumberColumn("Usage worth", format="%.1f"),
        "next_ppg": st.column_config.NumberColumn("Next 4 games", format="%.1f"),
        "change": st.column_config.NumberColumn("Change", format="%+.1f"),
        "chance_to_play": st.column_config.NumberColumn("Plays this game", format="percent"),
        "why": "Why",
    },
)
