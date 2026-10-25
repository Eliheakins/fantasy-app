import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from store_fixture import use_store, write_rows
from test_api import store_dir as store_dir  # noqa: F401  (fixture)

from fantasy import api, data_api, store
from fantasy.sim.value import market_hint
from fantasy.stages import market_values as stage
from fantasy.stages.market_values import Setting, fetch_values, setting_for, to_frame

TODAY = "2026-10-25T08:00:00+00:00"
YESTERDAY = "2026-10-24T08:00:00+00:00"


def item(sleeper_id: str | None, name: str = "A", position: str = "WR", value: float = 5000) -> Any:
    return {
        "player": {"sleeperId": sleeper_id, "name": name, "position": position},
        "value": value,
        "overallRank": 3,
        "positionRank": 2,
        "trend30Day": -12,
        "maybeTier": 1,
    }


def league(key: str, scoring: dict[str, float], positions: list[str]) -> Any:
    return {
        "league_key": key,
        "league_id": key,
        "num_teams": 10,
        "scoring_settings": json.dumps(scoring),
        "roster_positions": positions,
    }


def test_superflex_means_two_qbs_and_rec_points_map_to_ppr() -> None:
    sf = setting_for(json.dumps({"rec": 1.0}), ["QB", "SUPER_FLEX"], 10)
    one_qb = setting_for(json.dumps({"rec": 0.5}), ["QB", "FLEX"], 12)
    assert sf == Setting(num_qbs=2, num_teams=10, ppr=1.0)
    assert one_qb == Setting(num_qbs=1, num_teams=12, ppr=0.5)
    assert setting_for("{}", ["QB"], 10).ppr == 0.0


def test_to_frame_drops_null_ids_and_picks_and_keeps_the_rest() -> None:
    items = [item("1"), item(None, "Pick"), item("2", "2027 Pick 1.01", "PICK"), item("3")]
    frame = to_frame(items, "k", TODAY)
    assert frame["sleeper_id"].to_list() == ["1", "3"]
    assert frame.row(0, named=True) == {
        "format": "k", "sleeper_id": "1", "name": "A", "position": "WR", "value": 5000.0,
        "overall_rank": 3, "position_rank": 2, "trend_30_day": -12.0, "tier": 1,
        "fetched_at": TODAY,
    }  # fmt: skip


def write_leagues(path: Path) -> None:
    write_rows(
        path,
        "leagues",
        [
            league("a", {"rec": 1.0}, ["QB", "SUPER_FLEX"]),
            league("b", {"rec": 0.5}, ["QB", "FLEX"]),
            league("c", {"rec": 0.5}, ["QB", "FLEX"]),  # same setting as b: one fetch
        ],
    )


def test_one_fetch_per_distinct_setting_then_none_when_fetched_today(tmp_path: Path) -> None:
    write_leagues(tmp_path)
    calls: list[Setting] = []

    def fake(setting: Setting) -> list[Any]:
        calls.append(setting)
        return [item("1")]

    assert stage.run(tmp_path, fake, TODAY) == 2
    assert stage.run(tmp_path, fake, TODAY) == 0
    assert len(calls) == 2
    assert store.read_table("market_values", "raw", tmp_path).height == 2


def test_a_failed_fetch_keeps_the_previous_table_and_main_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_leagues(tmp_path)
    stage.run(tmp_path, lambda s: [item("1")], YESTERDAY)
    before = store.read_table("market_values", "raw", tmp_path)

    def boom(setting: Setting) -> list[Any]:
        raise RuntimeError("down")

    assert stage.run(tmp_path, boom, TODAY) == 0
    assert store.read_table("market_values", "raw", tmp_path).equals(before)

    def crash() -> int:
        raise OSError("disk")

    monkeypatch.setattr(stage, "run", crash)
    assert stage.main() == 0


def test_fetch_values_sends_the_query_and_a_user_agent_and_rejects_bad_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {"body": [item("1")]}

    class Resp:
        def raise_for_status(self) -> None: ...

        def json(self) -> Any:
            return seen["body"]

    def get(url: str, **kw: Any) -> Resp:
        seen.update(url=url, **kw)
        return Resp()

    monkeypatch.setattr(stage.httpx, "get", get)
    assert fetch_values(Setting(2, 10, 0.5)) == [item("1")]
    assert seen["params"] == {"isDynasty": "false", "numQbs": 2, "numTeams": 10, "ppr": 0.5}
    assert seen["headers"]["User-Agent"] and seen["timeout"] > 0
    seen["body"] = {"oops": 1}
    with pytest.raises(RuntimeError):
        fetch_values(Setting(2, 10, 0.5))


def seed_values(path: Path) -> None:
    write_rows(path, "id_map", [{"sleeper_id": "1", "gsis_id": "00-1"}])
    row = store.read_table("leagues", "raw", path).row(0, named=True)
    key = setting_for(row["scoring_settings"], row["roster_positions"], row["num_teams"]).key
    frame = to_frame([item("1", value=7000), item("2", value=900)], key, TODAY)
    store.write_table("market_values", frame, "raw", path)


def test_market_values_maps_to_gsis_and_is_empty_without_the_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_store(monkeypatch, tmp_path)
    write_rows(tmp_path, "leagues", [league("t", {}, ["QB"])])
    write_rows(tmp_path, "id_map", [{"sleeper_id": "1", "gsis_id": "00-1"}])
    assert data_api.market_values("t", ["00-1"], tmp_path).is_empty()
    seed_values(tmp_path)
    out = data_api.market_values("t", ["00-1", "nope"], tmp_path)
    assert out.columns == [
        "gsis_id", "value", "overall_rank", "position_rank", "trend_30_day", "fetched_at",
    ]  # fmt: skip
    assert out["gsis_id"].to_list() == ["00-1"] and out["value"].to_list() == [7000.0]


def test_route_returns_ok_with_empty_data_when_the_table_is_missing(store_dir: Path) -> None:  # noqa: F811
    with TestClient(api.create_app(), base_url="http://localhost") as client:
        r = client.get("/api/leagues/t/market-values", params={"ids": "00-1,00-2"})
    assert r.json()["status"] == "ok" and r.json()["data"] == []


def test_route_serves_values(store_dir: Path) -> None:  # noqa: F811
    seed_values(store_dir)
    with TestClient(api.create_app(), base_url="http://localhost") as client:
        data = client.get("/api/leagues/t/market-values", params={"ids": "00-1"}).json()["data"]
    assert data[0]["gsis_id"] == "00-1" and data[0]["value"] == 7000.0


@pytest.mark.parametrize(
    ("give", "get", "text"),
    [
        (1000, 1000, "even"),
        (1000, 1099, "even"),  # gap 9.1%
        (1000, 1112, "you receive 10% more"),  # gap 10.07%
        (1000, 2000, "you receive 50% more"),
        (2000, 1000, "you overpay 50%"),
        (1112, 1000, "you overpay 10%"),
    ],
)
def test_market_hint_bands(give: float, get: float, text: str) -> None:
    assert market_hint(give, get, 0) == text


def test_market_hint_reports_missing_values_and_handles_zero_totals() -> None:
    assert market_hint(1000, 2000, 2) == "you receive 50% more; no value for 2 players"
    assert market_hint(1000, 1000, 1) == "even; no value for 1 player"
    assert market_hint(0, 0, 0) == "even"
