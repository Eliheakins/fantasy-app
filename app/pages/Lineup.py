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

name_of = dict(zip(rows["gsis_id"], rows["full_name"], strict=True))
try:
    odds = data_api.win_probability(league_key, week)
except FileNotFoundError:
    odds = None
if odds is not None and not odds.is_empty():
    by_option = {r["option"]: r for r in odds.iter_rows(named=True)}
    pick, best = by_option["win_prob"], by_option["max_points"]
    st.subheader("Win probability against your opponent")
    st.metric("Chance to win with the recommended lineup", f"{best['win_prob']:.1%}")
    if pick["tag"] == "same as max points":
        st.caption("No swap raises the win probability: the highest-scoring lineup is also best.")
    else:
        ins = [name_of[i] for i in set(pick["gsis_ids"]) - set(best["gsis_ids"])]
        out = [name_of[i] for i in set(best["gsis_ids"]) - set(pick["gsis_ids"])]
        st.info(
            f"**{pick['tag'].capitalize()}**: start {', '.join(ins)} over {', '.join(out)} "
            f"({pick['win_prob']:.1%} vs {best['win_prob']:.1%}). In games where the two "
            f"lineups disagree, this one wins {pick['share_better']:.0%} of the time."
        )


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
        pl.when(pl.col("locked")).then(pl.lit("Locked")).otherwise(pl.lit("")).alias("lock"),
    ).select("slot", "full_name", "position", "injury", "projection", "range", "change", "lock")


config = {
    "slot": "Slot",
    "full_name": "Player",
    "position": "Pos",
    "injury": "Status",
    "projection": st.column_config.NumberColumn("Proj", format="%.1f"),
    "range": "10 to 90%",
    "change": "Change",
    "lock": "Game",
}
st.subheader("Start")
st.dataframe(table(start), hide_index=True, width="stretch", column_config=config)
if not bench.is_empty():
    st.subheader("Bench")
    st.dataframe(table(bench), hide_index=True, width="stretch", column_config=config)
st.caption(
    "Best lineup by projected points for skill positions; K and DEF are not handled yet, and "
    "players on bye are left out. Players whose game has started are locked in place: locked "
    "starters stay, locked bench players are not recommended. Injury status scales the "
    "projection (Out 0%, Doubtful 2%, Questionable 76% of normal, from past reports). The range "
    "is where about 80 percent of outcomes have landed for players like this. In the win "
    "probability, the opponent plays the lineup set in Sleeper and K and DEF are league averages. "
    + ("" if known else "Sleeper lineups are only known for the current week.")
)
