from datetime import UTC, datetime
from pathlib import Path

import pytest

from fantasy.auth import accounts, leagues, passwords

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "COST_N", 2**10)


@pytest.fixture
def db(tmp_path: Path):  # noqa: ANN201 - a sqlite3 connection
    conn = accounts.connect(tmp_path)
    yield conn
    conn.close()


def member(db, email: str) -> int:  # noqa: ANN001
    token = accounts.create_invite(db, email, NOW)
    return int(accounts.redeem_invite(db, token, "a long enough password", NOW)["id"])


def test_a_league_gets_a_stable_key_that_cannot_clash_with_config_names() -> None:
    assert leagues.key_for("1394105943137992704") == "sl-1394105943137992704"


def test_adding_a_league_registers_it_queued_and_grants_it_to_the_account(db) -> None:  # noqa: ANN001
    account = member(db, "a@example.com")
    row, created = leagues.add(db, account, "111", "Friends League", NOW)
    assert created
    assert (row["league_id"], row["league_key"], row["status"]) == ("111", "sl-111", "queued")
    assert accounts.granted_league_ids(db, account) == {"111"}
    assert [r["league_id"] for r in leagues.registered(db)] == ["111"]


def test_adding_the_same_league_again_changes_nothing(db) -> None:  # noqa: ANN001
    account = member(db, "a@example.com")
    leagues.add(db, account, "111", "Friends League", NOW)
    leagues.add(db, account, "111", "Friends League", NOW)
    assert len(leagues.registered(db)) == 1
    assert len(leagues.mine(db, account)) == 1


def test_adding_reports_whether_the_registry_row_is_new(db) -> None:  # noqa: ANN001
    first, second = member(db, "a@example.com"), member(db, "b@example.com")
    assert leagues.add(db, first, "111", "Shared", NOW)[1] is True
    assert leagues.add(db, first, "111", "Shared", NOW)[1] is False  # a repeat
    assert leagues.add(db, second, "111", "Shared", NOW)[1] is False  # a league-mate


def test_the_third_league_is_refused_but_a_repeat_of_one_you_have_is_not(db) -> None:  # noqa: ANN001
    account = member(db, "a@example.com")
    leagues.add(db, account, "111", "One", NOW)
    leagues.add(db, account, "222", "Two", NOW)
    with pytest.raises(leagues.LeagueLimit, match="up to 2"):
        leagues.add(db, account, "333", "Three", NOW)
    leagues.add(db, account, "222", "Two", NOW)  # already mine: not a new league
    assert {r["league_id"] for r in leagues.mine(db, account)} == {"111", "222"}


def test_two_accounts_in_one_league_share_one_registry_row(db) -> None:  # noqa: ANN001
    first, second = member(db, "a@example.com"), member(db, "b@example.com")
    leagues.add(db, first, "111", "Shared", NOW)
    leagues.add(db, second, "111", "Shared", NOW)
    assert len(leagues.registered(db)) == 1  # one ingestion, two people allowed to see it
    assert [r["league_id"] for r in leagues.mine(db, second)] == ["111"]


def test_leaving_a_shared_league_keeps_it_for_the_other_person(db) -> None:  # noqa: ANN001
    first, second = member(db, "a@example.com"), member(db, "b@example.com")
    leagues.add(db, first, "111", "Shared", NOW)
    leagues.add(db, second, "111", "Shared", NOW)
    assert leagues.release(db, first, "111") is True
    assert leagues.mine(db, first) == []
    assert [r["league_id"] for r in leagues.registered(db)] == ["111"]


def test_the_last_person_to_leave_takes_the_league_out_of_the_sync(db) -> None:  # noqa: ANN001
    account = member(db, "a@example.com")
    leagues.add(db, account, "111", "Mine", NOW)
    assert leagues.release(db, account, "111") is True
    assert leagues.registered(db) == []
    assert leagues.release(db, account, "111") is False  # nothing left to release


def test_leaving_frees_a_place_under_the_cap(db) -> None:  # noqa: ANN001
    account = member(db, "a@example.com")
    leagues.add(db, account, "111", "One", NOW)
    leagues.add(db, account, "222", "Two", NOW)
    leagues.release(db, account, "111")
    assert leagues.add(db, account, "333", "Three", NOW)[0]["league_id"] == "333"


def test_the_sync_reports_each_leagues_outcome_and_the_account_sees_it(db) -> None:  # noqa: ANN001
    account = member(db, "a@example.com")
    leagues.add(db, account, "111", "Good", NOW)
    leagues.add(db, account, "222", "Bad", NOW)
    leagues.mark(db, "111", None, NOW)
    leagues.mark(db, "222", "Sleeper did not answer", NOW)
    status = {r["league_id"]: (r["status"], r["error"]) for r in leagues.mine(db, account)}
    assert status == {"111": ("ready", None), "222": ("error", "Sleeper did not answer")}


def test_an_error_clears_when_the_next_sync_succeeds(db) -> None:  # noqa: ANN001
    account = member(db, "a@example.com")
    leagues.add(db, account, "111", "Flaky", NOW)
    leagues.mark(db, "111", "boom", NOW)
    leagues.mark(db, "111", None, NOW)
    [row] = leagues.mine(db, account)
    assert (row["status"], row["error"]) == ("ready", None)


def test_removing_an_account_removes_its_grants_and_orphaned_leagues(db) -> None:  # noqa: ANN001
    account = member(db, "a@example.com")
    leagues.add(db, account, "111", "Mine", NOW)
    accounts.remove_account(db, account)
    assert leagues.registered(db) == []
