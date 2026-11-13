"""The sync stage end to end with a fake Sleeper: the owner's config leagues are strict, and a
league someone added by username is isolated, so one bad league cannot stop the rest."""

from pathlib import Path
from typing import Any

import polars as pl
import pytest

from fantasy import store
from fantasy.config import Config
from fantasy.sources.sleeper import SleeperError
from fantasy.stages import sync_sleeper

OWNER = "owner-id"
FRIEND = "friend-id"
CONFIG_LEAGUE = "L-config"
FRIEND_LEAGUE = "L-friend"


def league_payload(league_id: str) -> dict[str, Any]:
    return {
        "league_id": league_id,
        "name": f"League {league_id}",
        "season": "2026",
        "status": "in_season",
        "settings": {"leg": 2, "num_teams": 2},
        "roster_positions": ["QB", "BN"],
        "scoring_settings": {"rec": 1.0},
    }


def roster(roster_id: int, owner: str) -> dict[str, Any]:
    return {
        "roster_id": roster_id,
        "owner_id": owner,
        "players": ["p1"],
        "starters": ["p1"],
        "settings": {"wins": 1, "losses": 0, **({"division": roster_id} if roster_id == 2 else {})},
    }


class FakeSleeper:
    """Answers by path; a path listed in `broken` raises, as Sleeper does for a deleted league."""

    def __init__(self, broken: set[str] | None = None, no_rosters: set[str] | None = None) -> None:
        self.broken = broken or set()
        self.no_rosters = no_rosters or set()
        self.paths: list[str] = []
        self.brackets: dict[str, Any] = {}
        self.settings: dict[str, Any] = {}  # merged into the league's settings

    def __call__(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self.paths.append(path)
        league_id = path.split("/")[2] if path.startswith("/league/") else ""
        if league_id in self.broken:
            raise SleeperError(f"Sleeper rejected the request: {path}")
        if path == f"/league/{league_id}":
            payload = league_payload(league_id)
            return {**payload, "settings": {**payload["settings"], **self.settings}}
        if path == f"/league/{league_id}/rosters":
            if league_id in self.no_rosters:
                return []
            owner = OWNER if league_id == CONFIG_LEAGUE else FRIEND
            return [roster(1, owner), roster(2, "someone-else")]
        if path == f"/league/{league_id}/users":
            return [
                {"user_id": OWNER, "display_name": "Owner"},
                {"user_id": FRIEND, "display_name": "Friend"},
            ]
        if path.endswith("_bracket"):
            return self.brackets.get(path.rsplit("/", 1)[1], [])
        return []  # matchups, transactions, trending


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.delenv(store.RELEASE_ENV, raising=False)
    player = {"position": "QB", "full_name": "P One", "team": "KC", "status": "Active"}
    monkeypatch.setattr(sync_sleeper, "load_players", lambda *a, **k: {"p1": player})
    return tmp_path


def config() -> Config:
    return Config(season=2026, user_id=OWNER, n_sims=100, leagues={"colgate": CONFIG_LEAGUE})


def run(fake: FakeSleeper, monkeypatch: pytest.MonkeyPatch, registered=(), report=None):
    monkeypatch.setattr(sync_sleeper, "fetch", fake)
    return sync_sleeper.run(config(), registered=registered, report=report or (lambda *a: None))


def table(name: str) -> pl.DataFrame:
    return store.read_table(name, "raw")


def test_a_registered_league_is_synced_with_no_team_marked_mine(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(FakeSleeper(), monkeypatch, registered=[("sl-L-friend", FRIEND_LEAGUE)])
    keys = dict(table("leagues").select("league_key", "league_id").iter_rows())
    assert keys == {"colgate": CONFIG_LEAGUE, "sl-L-friend": FRIEND_LEAGUE}
    mine = table("league_teams").filter(pl.col("is_me"))
    assert mine["league_id"].to_list() == [CONFIG_LEAGUE]  # only the owner's own league has one


def test_each_registered_league_is_reported_ok(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str | None]] = []
    run(
        FakeSleeper(),
        monkeypatch,
        registered=[("sl-L-friend", FRIEND_LEAGUE)],
        report=lambda lid, err: seen.append((lid, err)),
    )
    assert seen == [(FRIEND_LEAGUE, None)]


def test_a_broken_registered_league_is_reported_and_the_rest_still_sync(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str | None]] = []
    run(
        FakeSleeper(broken={FRIEND_LEAGUE}),
        monkeypatch,
        registered=[("sl-L-friend", FRIEND_LEAGUE)],
        report=lambda lid, err: seen.append((lid, err)),
    )
    assert table("leagues")["league_id"].to_list() == [CONFIG_LEAGUE]
    [(league_id, error)] = seen
    assert league_id == FRIEND_LEAGUE
    assert error is not None and "Sleeper" in error


def test_a_registered_league_with_no_rosters_is_an_error_not_a_crash(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str | None]] = []
    run(
        FakeSleeper(no_rosters={FRIEND_LEAGUE}),
        monkeypatch,
        registered=[("sl-L-friend", FRIEND_LEAGUE)],
        report=lambda lid, err: seen.append((lid, err)),
    )
    assert seen[0][1] is not None and "no rosters" in seen[0][1].lower()
    assert table("leagues")["league_id"].to_list() == [CONFIG_LEAGUE]


def test_a_broken_config_league_still_stops_the_sync(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SleeperError):
        run(
            FakeSleeper(broken={CONFIG_LEAGUE}),
            monkeypatch,
            registered=[("sl-L-friend", FRIEND_LEAGUE)],
        )


def test_a_league_in_both_places_is_synced_once_from_the_config(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str | None]] = []
    fake = FakeSleeper()
    run(
        fake,
        monkeypatch,
        registered=[("sl-L-config", CONFIG_LEAGUE)],
        report=lambda lid, err: seen.append((lid, err)),
    )
    assert table("leagues")["league_key"].to_list() == ["colgate"]
    assert fake.paths.count(f"/league/{CONFIG_LEAGUE}") == 1
    assert seen == [(CONFIG_LEAGUE, None)]


def test_with_nothing_registered_the_result_is_what_it_was_before(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    counts = run(FakeSleeper(), monkeypatch)
    assert table("leagues")["league_key"].to_list() == ["colgate"]
    assert counts["leagues"] == 1


def test_a_swallowed_league_error_logs_its_traceback(
    world: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    run(
        FakeSleeper(broken={FRIEND_LEAGUE}),
        monkeypatch,
        registered=[("sl-L-friend", FRIEND_LEAGUE)],
    )
    [record] = [r for r in caplog.records if FRIEND_LEAGUE in r.getMessage()]
    assert record.exc_info is not None


def test_run_writes_both_brackets_with_the_fetch_week(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeSleeper()
    fake.brackets = {
        "winners_bracket": [{"m": 1, "r": 1, "t1": 2, "t2": 1}],
        "losers_bracket": [{"m": 1, "r": 1, "t1": 4, "t2": 3}],
    }
    counts = run(fake, monkeypatch)
    df = table("playoff_brackets").sort("bracket")
    assert counts["playoff_brackets"] == 2
    assert df["bracket"].to_list() == ["losers", "winners"]
    assert df["fetched_week"].to_list() == [2, 2]  # league_payload leg


def test_a_malformed_bracket_keeps_the_league_ok(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeSleeper()
    fake.brackets = {"winners_bracket": [{"m": "bad"}], "losers_bracket": None}
    run(fake, monkeypatch)
    assert table("leagues")["league_id"].to_list() == [CONFIG_LEAGUE]
    assert table("playoff_brackets").height == 0


def test_a_stored_bracket_survives_a_malformed_payload(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = FakeSleeper()
    good.brackets = {"winners_bracket": [{"m": 1, "r": 1, "t1": 2, "t2": 1}]}
    run(good, monkeypatch)
    bad = FakeSleeper()
    bad.brackets = {"winners_bracket": [{"m": "bad"}]}
    run(bad, monkeypatch)
    assert table("playoff_brackets")["m"].to_list() == [1]


def test_an_empty_or_null_bracket_payload_clears_the_stored_bracket(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = FakeSleeper()
    good.brackets = {"winners_bracket": [{"m": 1, "r": 1, "t1": 2, "t2": 1}]}
    run(good, monkeypatch)
    empty = FakeSleeper()
    empty.brackets = {"winners_bracket": None}
    empty.settings = {"playoff_week_start": 3}  # week 2: the playoffs have not started
    run(empty, monkeypatch)
    assert table("playoff_brackets").height == 0


@pytest.mark.parametrize("payload", [None, []])
def test_an_empty_or_null_bracket_payload_keeps_the_stored_rows_in_the_playoffs(
    world: Path, monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    good = FakeSleeper()
    good.brackets = {"winners_bracket": [{"m": 1, "r": 1, "t1": 2, "t2": 1}]}
    run(good, monkeypatch)
    empty = FakeSleeper()
    empty.brackets = {"winners_bracket": payload}
    empty.settings = {"playoff_week_start": 2}  # week 2 is the first playoff week
    run(empty, monkeypatch)
    assert table("playoff_brackets")["m"].to_list() == [1]


def test_the_live_tick_makes_no_bracket_call(world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run(FakeSleeper(), monkeypatch)
    fake = FakeSleeper()
    monkeypatch.setattr(sync_sleeper, "fetch", fake)
    sync_sleeper.sync_week(2)
    assert fake.paths and not any("bracket" in p for p in fake.paths)


def test_run_stores_each_rosters_division_and_skips_rosters_without_one(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    counts = run(FakeSleeper(), monkeypatch)
    df = table("roster_divisions")
    assert counts["roster_divisions"] == 1
    assert df.to_dicts() == [{"league_id": CONFIG_LEAGUE, "roster_id": 2, "division": 2}]
