import polars as pl
import streamlit as st
from ui import (
    league_picker,
    no_data_warning,
    player_weeks,
    streamers,
    strength_table,
    waivers,
)

league_key, _week = league_picker()
st.title("Waivers")
try:
    adds = waivers(league_key)
except FileNotFoundError:
    no_data_warning()
    st.stop()

st.subheader("Where your roster is strong or thin")
strength_table(league_key)
st.caption(
    "Your best lineup each week against the stand-in free agent at each position (the third-best "
    "or so on the wire, since the top ones are the adds). Rank 1 is the strongest team. Thin "
    "positions are where an add helps; deep ones are where a trade can come from."
)

st.subheader("Adds")
st.caption(
    "Free agents ranked by expected points over the rest of the season above what you would "
    "have anyway. Every slot can always be filled by a stand-in free agent (bye weeks, injuries "
    "and weak starters included), so a backup at a position with plenty of free agents adds "
    "almost nothing, and the drop is whoever costs least. Playoff and title changes re-run the "
    "season simulation with the move made, on the same random draws as the unchanged roster. "
    "The title change carries a Monte Carlo error of up to the value in the last column, so "
    "title changes smaller than that are noise. Injured players are scaled by their status."
)
if adds.is_empty():
    st.info("No free agent adds expected points to your team.")
else:
    event = st.dataframe(
        adds.select(
            "full_name",
            "position",
            "drop_name",
            "delta_points",
            "playoff_delta",
            "title_delta",
            "se_title",
            "trending_adds",
        ),
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "full_name": "Add",
            "position": "Pos",
            "drop_name": "Drop",
            "delta_points": st.column_config.NumberColumn("Extra points", format="%+.1f"),
            "playoff_delta": st.column_config.NumberColumn("Playoffs", format="percent"),
            "title_delta": st.column_config.NumberColumn("Title", format="percent"),
            "se_title": st.column_config.NumberColumn("Title error", format="percent"),
            "trending_adds": st.column_config.NumberColumn("Sleeper adds", format="%d"),
        },
    )
    st.caption(
        "Sleeper adds is how many users added the player in the latest trending pull, a rough "
        "sign of who else will bid. Select a row to see the next four weeks."
    )
    chosen = event.selection.rows
    if chosen:
        pick = adds.row(chosen[0], named=True)
        weeks = player_weeks(league_key, pick["gsis_id"])
        st.subheader(f"{pick['full_name']}: next four weeks")
        st.bar_chart(weeks.with_columns(pl.col("week").cast(pl.String)), x="week", y="projection")

st.header("Streaming: defense and kicker")
st.caption(
    "Projected points over the next three weeks (a bye week counts as zero). The projection is "
    "recent form plus the game's implied total, and beats a plain league average only slightly "
    "for defenses (about 3% lower error) and not at all for kickers, so treat small gaps as "
    "noise. Your own player is marked."
)
for kind, label in (("DEF", "Defenses"), ("K", "Kickers")):
    try:
        picks = streamers(league_key, kind)
    except FileNotFoundError:
        st.info("Run the streaming stage to see this.")
        break
    st.subheader(label)
    st.dataframe(
        picks.select("name", "team", "is_mine", "this_week", "next_three"),
        hide_index=True,
        width="stretch",
        column_config={
            "name": label[:-1],
            "team": "Team",
            "is_mine": "Mine",
            "this_week": st.column_config.NumberColumn("This week", format="%.1f"),
            "next_three": st.column_config.NumberColumn("Next 3 weeks", format="%.1f"),
        },
    )
