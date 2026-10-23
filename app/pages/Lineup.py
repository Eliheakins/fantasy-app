import altair as alt
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

name_of = dict(zip(rows["gsis_id"], rows["full_name"], strict=True))
try:
    odds = data_api.win_probability(league_key, week)
except FileNotFoundError:
    odds = None
by_option = {} if odds is None else {r["option"]: r for r in odds.iter_rows(named=True)}
pick, best = by_option.get("win_prob"), by_option.get("max_points")
differs = pick is not None and pick["tag"] != "same as max points"

objective = "Expected points"
if differs:
    objective = st.radio("Optimize for", ["Expected points", "Win probability"], horizontal=True)
if objective == "Win probability" and pick is not None:
    slot_of = dict(zip(pick["gsis_ids"], pick["slots"], strict=True))
    rows = rows.with_columns(
        pl.col("gsis_id").is_in(list(slot_of)).alias("recommended"),
        pl.col("gsis_id").replace_strict(slot_of, default="BN").alias("slot"),
    )

start = rows.filter(pl.col("recommended"))
bench = rows.filter(~pl.col("recommended"))
known = bool(rows["starting_now"].any())
best_total = float(start["projection"].sum())
current_total = float(rows.filter(pl.col("starting_now"))["projection"].sum())

cols = st.columns(3)
cols[0].metric("Lineup shown", f"{best_total:.1f} pts")
if known:
    gap = current_total - best_total
    cols[1].metric("Set in Sleeper now", f"{current_total:.1f} pts", delta=f"{gap:+.1f}")
if best is not None and pick is not None:
    shown = pick if objective == "Win probability" else best
    cols[2].metric("Chance to win", f"{shown['win_prob']:.1%}")
    if not differs:
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
    ).select(
        "slot", "full_name", "position", "injury", "projection", "range", "actual", "game", "change"
    )


config = {
    "slot": "Slot",
    "full_name": "Player",
    "position": "Pos",
    "injury": "Status",
    "projection": st.column_config.NumberColumn("Proj", format="%.1f"),
    "range": "10 to 90%",
    "change": "Change",
    "actual": st.column_config.NumberColumn("Pts so far", format="%.1f"),
    "game": "Game",
}
st.subheader("Start")
st.dataframe(table(start), hide_index=True, width="stretch", column_config=config)

spread = start.select("full_name", "p10", "p90", "projection").to_pandas()
base = alt.Chart(spread).encode(y=alt.Y("full_name:N", sort=None, title=None))
st.altair_chart(
    base.mark_rule(strokeWidth=5, opacity=0.35).encode(
        x=alt.X("p10:Q", title="Points (10 to 90% range, dot is the projection)"), x2="p90:Q"
    )
    + base.mark_point(filled=True, size=70).encode(x="projection:Q"),
    width="stretch",
)
if not bench.is_empty():
    st.subheader("Bench")
    st.dataframe(table(bench), hide_index=True, width="stretch", column_config=config)
st.caption(
    "Best lineup by projected points for skill positions; K and DEF are not handled yet, and "
    "players on bye are left out. Players whose game has started are locked in place: locked "
    "starters stay, locked bench players are not recommended. A game counts as over 200 "
    "minutes after kickoff, and points are as fresh as the last refresh. Injury status scales the "
    "projection (Out 0%, Doubtful 2%, Questionable 76% of normal, from past reports). The range "
    "is where about 80 percent of outcomes have landed for players like this. In the win "
    "probability, the opponent plays the lineup set in Sleeper and K and DEF are league averages. "
    + ("" if known else "Sleeper lineups are only known for the current week.")
)
