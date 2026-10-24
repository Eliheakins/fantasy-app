from typing import Any

import altair as alt
import polars as pl
import streamlit as st
from ui import cached_lineup, cached_win_probability, league_picker, no_data_warning

league_key, week = league_picker()
st.title("Lineup")
try:
    rows = cached_lineup(league_key, week)
except FileNotFoundError:
    no_data_warning()
    st.stop()

if rows.is_empty():
    st.info(f"No projections for week {week}: either a past week or your players are on bye.")
    st.stop()

name_of = dict(zip(rows["gsis_id"], rows["full_name"], strict=True))
try:
    odds = cached_win_probability(league_key, week)
except FileNotFoundError:
    odds = pl.DataFrame()
by_option = {r["option"]: r for r in odds.iter_rows(named=True)}
pick, best = by_option.get("win_prob"), by_option.get("max_points")
LABELS = {
    "Expected points": "max_points",
    "Win probability": "win_prob",
    "Max ceiling": "ceiling",
    "Max floor": "floor",
}

objective = "Expected points"
if best is not None:
    if best["script"]:
        st.subheader(best["script"])
    objective = st.radio("Optimize for", list(LABELS), horizontal=True, key="lineup_objective")
shown_option = by_option.get(LABELS[objective]) if best is not None else None
if shown_option is not None and LABELS[objective] != "max_points":
    slot_of = dict(zip(shown_option["gsis_ids"], shown_option["slots"], strict=True))
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
if pick is not None and best is not None and shown_option is not None:
    differs = pick["tag"] != "same as max points"
    cols[2].metric("Chance to win", f"{shown_option['win_prob']:.1%}")
    if differs:
        ins = [name_of[i] for i in set(pick["gsis_ids"]) - set(best["gsis_ids"])]
        out = [name_of[i] for i in set(best["gsis_ids"]) - set(pick["gsis_ids"])]
        st.info(
            f"**{pick['tag'].capitalize()}**: start {', '.join(ins)} over {', '.join(out)} "
            f"({pick['win_prob']:.1%} vs {best['win_prob']:.1%}). In games where the two "
            f"lineups disagree, this one wins {pick['share_better']:.0%} of the time."
        )
    else:
        st.caption(
            "No swap raises the win probability enough to matter: one flex slot is a small part "
            "of a team score that spreads about 30 points, so trading expected points for "
            "upside rarely pays. The comparison below shows what each choice does."
        )
    comparison = odds.filter(pl.col("option") != "sleeper_now").with_columns(
        pl.col("option").replace_strict({v: k for k, v in LABELS.items()}, default=pl.col("option"))
    )
    st.dataframe(
        comparison.select("option", "win_prob", "floor", "median", "ceiling"),
        hide_index=True,
        width="stretch",
        column_config={
            "option": "Lineup",
            "win_prob": st.column_config.NumberColumn("Chance to win", format="percent"),
            "floor": st.column_config.NumberColumn("Floor (10%)", format="%.0f"),
            "median": st.column_config.NumberColumn("Median", format="%.0f"),
            "ceiling": st.column_config.NumberColumn("Ceiling (90%)", format="%.0f"),
        },
    )
    st.caption(
        "Team score including points already scored and K and DEF. Floor and ceiling are the "
        "10th and 90th percentiles. Win probability, ceiling and floor lineups are chosen on "
        "half the simulated games and scored on the other half."
    )


def table(frame: pl.DataFrame) -> pl.DataFrame:
    low, high = pl.col("p10").round(1).cast(pl.String), pl.col("p90").round(1).cast(pl.String)
    seen = pl.lit(known)
    start_it = seen & pl.col("recommended") & ~pl.col("starting_now")
    sit_it = seen & pl.col("starting_now") & ~pl.col("recommended")
    return frame.with_columns(
        pl.when(start_it)
        .then(pl.lit("Start"))
        .when(sit_it)
        .then(pl.lit("Sit"))
        .otherwise(pl.lit(""))
        .alias("change"),
        (low + " to " + high).alias("range"),
    ).select(
        "slot",
        "full_name",
        "position",
        "injury_note",
        "projection",
        "range",
        "actual",
        "game",
        "change",
    )


config: dict[str, Any] = {
    "slot": "Slot",
    "full_name": "Player",
    "position": "Pos",
    "injury_note": "Injury",
    "projection": st.column_config.NumberColumn("Proj", format="%.1f"),
    "range": "10 to 90%",
    "change": "Change",
    "actual": st.column_config.NumberColumn("Pts so far", format="%.1f"),
    "game": "Game",
}
st.subheader("Start")
st.dataframe(table(start), hide_index=True, width="stretch", column_config=config)

spread = start.select("full_name", "p10", "p90", "projection")
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
    "minutes after kickoff, and points are as fresh as the last refresh. The "
    "injury column shows the chance of playing this game and the next, measured from 2018 to "
    "2025 reports by injury type and practice (hamstrings and feet linger, a Questionable "
    "player who did not practice rarely plays), and players who play through an injury are "
    "discounted a little. The range "
    "is where about 80 percent of outcomes have landed for players like this. In the win "
    "probability, the opponent plays the lineup set in Sleeper and K and DEF are league averages. "
    + ("" if known else "Sleeper lineups are only known for the current week.")
)
