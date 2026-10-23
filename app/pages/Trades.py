import polars as pl
import streamlit as st
from ui import league_picker, no_data_warning

from fantasy import data_api

CACHE_SECONDS = 300


@st.cache_data(ttl=CACHE_SECONDS)
def evaluate(league_key: str, partner: int, give: tuple[str, ...], get: tuple[str, ...]):
    odds = data_api.evaluate_trade(league_key, partner, list(give), list(get))
    changes = data_api.trade_roster_changes(league_key, partner, list(give), list(get))
    return odds, changes


@st.cache_data(ttl=CACHE_SECONDS)
def find(league_key: str):
    return data_api.find_trades(league_key)


def labels(assets: pl.DataFrame) -> dict[str, str]:
    return {
        r["gsis_id"]: f"{r['full_name']} ({r['position']}, {r['ros_points']:.0f} pts)"
        for r in assets.iter_rows(named=True)
    }


def show_side(title: str, row: dict) -> None:
    st.subheader(title)
    for label, key, scale, unit in (
        ("Make playoffs", "playoff", 100, "%"),
        ("Win the title", "title", 100, "%"),
        ("Expected wins", "wins", 1, ""),
    ):
        before, after = row[f"{key}_before"], row[f"{key}_after"]
        st.metric(
            label,
            f"{after * scale:.1f}{unit}",
            delta=f"{(after - before) * scale:+.1f}{unit if unit else ''}",
        )


league_key, _week = league_picker()
st.title("Trades")
try:
    partners = data_api.trade_partners(league_key)
    mine = data_api.trade_assets(league_key)
except FileNotFoundError:
    no_data_warning()
    st.stop()

st.subheader("Where your roster is strong or thin")
st.dataframe(
    data_api.position_strength(league_key),
    hide_index=True,
    width="stretch",
    column_config={
        "position": "Position",
        "vor_per_week": st.column_config.NumberColumn(
            "Points a week over replacement", format="%.1f"
        ),
        "rank": "League rank",
        "teams": "Teams",
    },
)
st.caption("Deep positions (rank near 1) are where a trade can come from; thin ones are the needs.")

st.subheader("Find trades")
st.caption(
    "Trades of one or two players each way (1 for 1, 1 for 2, 2 for 1, 2 for 2) between each "
    "team's top six players that raise both teams' playoff plus title odds, best for you first. "
    "A side left with an open roster spot is compared with itself after its own best waiver "
    "move, so a free pickup is not credited to the trade. Managers accept trades based on how "
    "they value players, which is not modeled. Changes are in percentage points; error is the "
    "Monte Carlo error of your title change."
)
if st.button("Find trades"):
    try:
        found = find(league_key)
    except ValueError as err:
        st.warning(str(err))
    else:
        if found.is_empty():
            st.info("No trade helps both teams right now.")
        else:
            percent = ["my_playoff", "my_title", "their_playoff", "their_title", "se_title"]
            st.dataframe(
                found.with_columns(pl.col(percent) * 100),
                hide_index=True,
                width="stretch",
                column_config={
                    "partner": "Partner",
                    "give": "You give",
                    "get": "You get",
                    "my_playoff": st.column_config.NumberColumn("Your playoffs", format="%+.1f%%"),
                    "my_title": st.column_config.NumberColumn("Your title", format="%+.1f%%"),
                    "their_playoff": st.column_config.NumberColumn(
                        "Their playoffs", format="%+.1f%%"
                    ),
                    "their_title": st.column_config.NumberColumn("Their title", format="%+.1f%%"),
                    "se_title": st.column_config.NumberColumn("Error", format="%.2f%%"),
                },
            )

st.subheader("Evaluate a trade")
team_names = dict(zip(partners["roster_id"], partners["team_name"], strict=True))
partner = st.selectbox("Trade partner", list(team_names), format_func=team_names.get)
theirs = data_api.trade_assets(league_key, int(partner))
mine_labels, their_labels = labels(mine), labels(theirs)
left, right = st.columns(2)
give = left.multiselect(
    "I give", list(mine_labels), format_func=mine_labels.get, key=f"give_{league_key}"
)
get = right.multiselect(
    f"I get from {team_names[partner]}",
    list(their_labels),
    format_func=their_labels.get,
    key=f"get_{league_key}_{partner}",
)
st.caption(
    "Points are projected totals for the rest of the season. Each roster keeps its size: "
    "extra players are dropped and open spots filled with the best free agent. "
    "Odds assume current rosters."
)

if st.button("Evaluate", disabled=not (give and get)):
    try:
        odds, changes = evaluate(league_key, int(partner), tuple(give), tuple(get))
    except ValueError as err:
        st.warning(str(err))
    else:
        rows = {r["side"]: r for r in odds.iter_rows(named=True)}
        col_me, col_them = st.columns(2)
        with col_me:
            show_side("Me", rows["me"])
        with col_them:
            show_side(rows["them"]["team_name"], rows["them"])
        if not changes.is_empty():
            st.warning("Automatic roster moves to keep sizes equal:")
            st.dataframe(changes, hide_index=True, width="stretch")
