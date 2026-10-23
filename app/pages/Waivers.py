import streamlit as st
from ui import league_picker, no_data_warning

from fantasy import data_api

league_key, _week = league_picker()
st.title("Waivers")
try:
    adds = data_api.waivers(league_key)
except FileNotFoundError:
    no_data_warning()
    st.stop()

st.caption(
    "Free agents ranked by extra projected points over the rest of the season, each paired with "
    "the drop that costs the least (bye weeks included). Playoff and title changes re-run the "
    "season simulation with the move made, on the same random draws as the unchanged roster. "
    "The title change carries a Monte Carlo error of up to the value in the last column, so "
    "title changes smaller than that are noise. Injured players are scaled by their status."
)
if adds.is_empty():
    st.info("No free agent adds expected points to your team.")
    st.stop()
st.dataframe(
    adds.select(
        "full_name",
        "position",
        "drop_name",
        "delta_points",
        "playoff_delta",
        "title_delta",
        "se_title",
    ),
    hide_index=True,
    width="stretch",
    column_config={
        "full_name": "Add",
        "position": "Pos",
        "drop_name": "Drop",
        "delta_points": st.column_config.NumberColumn("Extra points", format="%+.1f"),
        "playoff_delta": st.column_config.NumberColumn("Playoffs", format="percent"),
        "title_delta": st.column_config.NumberColumn("Title", format="percent"),
        "se_title": st.column_config.NumberColumn("Title error", format="percent"),
    },
)
