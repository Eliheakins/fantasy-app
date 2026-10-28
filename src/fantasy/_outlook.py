"""Season outlook for my team and the league's players: schedule, live score, player outlook."""

import polars as pl

from fantasy import store
from fantasy._engine import _injury_note, _league, _names, _opponent_of, _pool
from fantasy._schemas import OUTLOOK_SCHEMA
from fantasy.config import load_config
from fantasy.sim import moves
from fantasy.sim.lineup import auto_lineup, constant_slot_count, lineup_slots
from fantasy.sim.odds import kd_slot_mean

OUTLOOK_RECENT_GAMES = 4
OUTLOOK_THRESHOLD = 1.5  # points a game of expected change before a player is called improving
OUTLOOK_INJURED = 0.35  # chance to play this game at or below which a player is just Injured
OUTLOOK_MIN_PROJECTION = 4.0  # league and free-agent views skip players projected below this
OUTLOOK_MIN_GAMES = 2  # recent games needed before a change or a usage gap means anything
USAGE_GAP = 2.0  # points a game above or below expected points worth a note
# projection columns a layer that did not run leaves out, with the value that means "no effect"
LAYER_DEFAULTS = {
    "outlook_factor": 1.0,
    "vacancy_points": 0.0,
    "offense_points": 0.0,
    "matchup_points": 0.0,
}


def schedule(league_key: str) -> pl.DataFrame:
    """My remaining regular-season games: opponent, both teams' expected points and my chance.

    The chance is a normal approximation from each lineup's mean and spread (injury-scaled
    projections, K and DEF at each team's projection); the season simulation is the sharper number.
    """
    from scipy.stats import norm

    from fantasy.sim.odds import DRIFT_SD, lineup_moments

    data, mine = _league(league_key)
    positions, by_week = moves.position_of(data), moves.week_values(data)
    slots = lineup_slots(data.roster_positions)
    counts = constant_slot_count(data.roster_positions)
    kd_var = counts.get("K", 0) * data.k_var + counts.get("DEF", 0) * data.def_var

    def moments(roster_id: int, week: int) -> tuple[float, float]:
        pool = _pool(data, roster_id, positions, by_week.get(week, {}))
        best = auto_lineup(pool, slots)
        chosen = [p for p in pool if p.id in best.players]
        mean, var, _ = lineup_moments(
            chosen, data.cv, data.pair_rho, data.cv_tiers
        )  # var is already total
        kd_mean = counts.get("K", 0) * kd_slot_mean(data, "K", roster_id, week) + counts.get(
            "DEF", 0
        ) * kd_slot_mean(data, "DEF", roster_id, week)
        return mean + kd_mean, var + kd_var + DRIFT_SD**2

    rows = []
    for week in range(data.current_week, data.playoff_start):
        for a, b in data.pairings.get(week, []):
            if mine not in (a, b):
                continue
            opp = b if a == mine else a
            (m1, v1), (m2, v2) = moments(mine, week), moments(opp, week)
            chance = float(norm.cdf((m1 - m2) / (v1 + v2) ** 0.5))
            rows.append((week, data.team_names[opp], m1, m2, chance))
    schema = ["week", "opponent", "my_points", "their_points", "win_chance"]
    return pl.DataFrame(rows, schema=schema, orient="row")


def live_score(league_key: str) -> pl.DataFrame:
    """This week's score so far and projected final for me and my opponent.

    Columns: side ("me" or "them"), team_name, points (so far), projected_final. The projected
    final adds the unconditional projection of what is left in each set lineup. Empty before
    the week has any matchup data.
    """
    data, mine = _league(league_key)
    opp = _opponent_of(data, mine, data.current_week)
    rows = []
    for side, rid in (("me", mine), ("them", opp)):
        state = data.current.get(rid) if rid is not None else None
        if rid is None or state is None:
            continue
        left = (
            sum(p.value for p in state.open_players)
            + state.open_k * kd_slot_mean(data, "K", rid, data.current_week)
            + state.open_def * kd_slot_mean(data, "DEF", rid, data.current_week)
        )
        rows.append((side, data.team_names[rid], state.realized, state.realized + left))
    return pl.DataFrame(
        rows, schema=["side", "team_name", "points", "projected_final"], orient="row"
    )


def _why(r: dict, injury_note: str | None) -> str:
    """The drivers behind a player's expected change, in words."""
    why = []
    if r["factor"] < 0.97:
        why.append(f"first games back ({r['factor']:.0%} of projection)")
    if r["vacancy"] >= 0.5:
        why.append(f"teammates out (+{r['vacancy']:.1f} points)")
    if r["matchup"] >= 0.25:
        why.append(f"opposing corner out (+{r['matchup']:.1f} points)")
    if abs(r["offense"]) >= 0.4:
        side = "gain" if r["offense"] > 0 else "loss"
        why.append(f"offense efficiency regression ({side} of {abs(r['offense']):.1f} points)")
    recent, expected = r["recent_ppg"], r["expected_ppg"]
    if recent is not None and expected is not None and (r["games"] or 0) >= OUTLOOK_MIN_GAMES:
        if recent - expected >= USAGE_GAP:
            why.append(f"scoring {recent - expected:.1f} above what usage is worth")
        elif expected - recent >= USAGE_GAP:
            why.append(f"scoring {expected - recent:.1f} below what usage is worth")
    if injury_note:
        why.append(injury_note)
    return "; ".join(why)


def _label(r: dict, change: float | None) -> str:
    """Injured, No recent games, Improving, Regressing or Steady."""
    if (r["chance_to_play"] or 0.0) <= OUTLOOK_INJURED:
        return "Injured"
    if change is None:
        return "No recent games"
    if change >= OUTLOOK_THRESHOLD:
        return "Improving"
    return "Regressing" if change <= -OUTLOOK_THRESHOLD else "Steady"


def player_outlook(league_key: str, scope: str = "mine") -> pl.DataFrame:
    """Who is improving or regressing over the next four games, and why.

    scope is "mine" (my roster), "league" (rostered by others) or "free" (free agents).
    recent_ppg is points a game over the last four games played; expected_ppg is what their
    usage was worth over the same games; next_ppg is the projection per game when he plays over
    his next four games (return ramps, teammates out and injury discounts included); change is
    next_ppg minus recent_ppg. The label is Improving or Regressing past OUTLOOK_THRESHOLD, or
    Injured when he is unlikely to play this game.
    Only three drivers are modeled (see docs/decisions.md): a return from missed games,
    teammates who are out, and the gap between points and expected points.
    """
    from fantasy.stages.project import expected_frame

    data, mine = _league(league_key)
    lid = data.league_id
    points = store.read_table("player_points", "derived").filter(pl.col("league_id") == lid)
    leagues_raw = store.read_table("leagues", "raw").filter(pl.col("league_id") == lid)
    exp = expected_frame(store.read_table("nfl_ff_opportunity", "raw"), points, leagues_raw)
    season = load_config().season
    recent = (
        exp.filter((pl.col("season") == season) & (pl.col("week") < data.current_week))
        .sort("gsis_id", "week")
        .group_by("gsis_id")
        .agg(
            pl.col("points").tail(OUTLOOK_RECENT_GAMES).mean().alias("recent_ppg"),
            pl.col("exp_pts").tail(OUTLOOK_RECENT_GAMES).mean().alias("expected_ppg"),
            pl.len().alias("games"),
        )
    )
    proj = data.projections.with_columns(
        pl.lit(default).alias(column)
        for column, default in LAYER_DEFAULTS.items()
        if column not in data.projections.columns
    )
    ahead = (
        proj.filter(pl.col("week") >= data.current_week)
        .sort("gsis_id", "week")
        .group_by("gsis_id", maintain_order=True)
        .head(OUTLOOK_RECENT_GAMES)
    )
    summary = ahead.group_by("gsis_id").agg(
        (pl.col("projection").sum() / pl.col("play_prob").sum().clip(lower_bound=1e-9)).alias(
            "next_ppg"
        ),
        pl.col("play_prob").first().alias("chance_to_play"),
        pl.col("outlook_factor").first().alias("factor"),
        pl.col("vacancy_points").mean().alias("vacancy"),
        pl.col("offense_points").mean().alias("offense"),
        pl.col("matchup_points").mean().alias("matchup"),
    )
    owner_of = dict(zip(data.rosters["gsis_id"], data.rosters["roster_id"], strict=True))
    owner_names = {**data.team_names, mine: "You"}
    names = _names()
    positions = moves.position_of(data)
    wanted = {
        "mine": lambda owner: owner == mine,
        "league": lambda owner: owner is not None and owner != mine,
        "free": lambda owner: owner is None,
    }[scope]
    rows = []
    for r in summary.join(recent, on="gsis_id", how="left").iter_rows(named=True):
        g = r["gsis_id"]
        owner = owner_of.get(g)
        if not wanted(owner) or g not in names or g not in positions:
            continue
        if scope != "mine" and (r["next_ppg"] or 0.0) < OUTLOOK_MIN_PROJECTION:
            continue
        recent_ppg = r["recent_ppg"]
        enough = recent_ppg is not None and (r["games"] or 0) >= OUTLOOK_MIN_GAMES
        change = r["next_ppg"] - recent_ppg if enough else None
        rows.append(
            {
                "gsis_id": g,
                "full_name": names[g],
                "position": positions[g],
                "owner": "Free agent" if owner is None else owner_names.get(owner, "Free agent"),
                "recent_ppg": recent_ppg,
                "expected_ppg": r["expected_ppg"],
                "next_ppg": r["next_ppg"],
                "change": change,
                "chance_to_play": r["chance_to_play"],
                "label": _label(r, change),
                "why": _why(r, _injury_note(data, g)),
            }
        )
    return pl.DataFrame(rows, schema=OUTLOOK_SCHEMA).sort(
        "change", descending=True, nulls_last=True
    )
