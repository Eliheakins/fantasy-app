import polars as pl
import streamlit as st
from ui import league_picker, no_data_warning

from fantasy import data_api

league_key, week = league_picker()
st.title("Lineup")
try:
    rows = data_api.lineup(league_key, week)
except FileNotFoundError:
    no_data_warning()
    st.stop()

if rows.is_empty():
    st.info(f"No projections for week {week}: either a past week or your players are on bye.")
    st.stop()

start = rows.filter(pl.col("recommended"))
bench = rows.filter(~pl.col("recommended"))
known = bool(rows["starting_now"].any())
best_total = float(start["projection"].sum())
current_total = float(rows.filter(pl.col("starting_now"))["projection"].sum())

cols = st.columns(2)
cols[0].metric("Recommended lineup", f"{best_total:.1f} pts")
if known:
    gap = current_total - best_total
    cols[1].metric("Set in Sleeper now", f"{current_total:.1f} pts", delta=f"{gap:+.1f}")


def change(row: dict) -> str:
    if not known:
        return ""
    if row["recommended"] and not row["starting_now"]:
        return "Start"
    if row["starting_now"] and not row["recommended"]:
        return "Sit"
    return ""


def table(frame: pl.DataFrame) -> pl.DataFrame:
    low, high = pl.col("p10").round(1).cast(pl.String), pl.col("p90").round(1).cast(pl.String)
    return frame.with_columns(
        pl.struct(frame.columns).map_elements(change, return_dtype=pl.String).alias("change"),
        (low + " to " + high).alias("range"),
    ).select("slot", "full_name", "position", "projection", "range", "change")


config = {
    "slot": "Slot",
    "full_name": "Player",
    "position": "Pos",
    "projection": st.column_config.NumberColumn("Proj", format="%.1f"),
    "range": "10 to 90%",
    "change": "Change",
}
st.subheader("Start")
st.dataframe(table(start), hide_index=True, width="stretch", column_config=config)
if not bench.is_empty():
    st.subheader("Bench")
    st.dataframe(table(bench), hide_index=True, width="stretch", column_config=config)
st.caption(
    "Best lineup by projected points for skill positions; K and DEF are not handled yet, and "
    "players on bye are left out. It does not know which games have already started, so check "
    "kickoff times before moving a player whose game is under way. The range is where about 80 "
    "percent of outcomes have landed for players like this. A win-probability version comes "
    "later. " + ("" if known else "Sleeper lineups are only known for the current week.")
)
