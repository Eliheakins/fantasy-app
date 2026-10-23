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
    "Free agents ranked by extra projected points over the rest of the season if added in place "
    "of your lowest-value player. A shortcut: it ignores bye-week coverage and injuries. "
    "Playoff and title odds per add come later."
)
st.dataframe(
    adds.select("full_name", "position", "delta_points", "drop_name"),
    hide_index=True,
    width="stretch",
    column_config={
        "full_name": "Add",
        "position": "Pos",
        "delta_points": st.column_config.NumberColumn("Extra points", format="%+.1f"),
        "drop_name": "Drop",
    },
)
