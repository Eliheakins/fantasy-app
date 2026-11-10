from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fantasy.auth import accounts, passwords

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
GOOD = "a long enough password"


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "COST_N", 2**10)


@pytest.fixture
def db(tmp_path: Path):  # noqa: ANN201 - a sqlite3 connection
    conn = accounts.connect(tmp_path)
    yield conn
    conn.close()


def test_there_is_no_auth_until_the_first_account_exists(tmp_path: Path) -> None:
    assert accounts.has_accounts(tmp_path) is False
    conn = accounts.connect(tmp_path)
    accounts.create_admin(conn, "Boss@Example.com", GOOD)
    conn.close()
    assert accounts.has_accounts(tmp_path) is True


def test_an_admin_can_log_in_with_any_email_casing(db) -> None:  # noqa: ANN001
    accounts.create_admin(db, "Boss@Example.com", GOOD)
    account = accounts.login(db, "  boss@EXAMPLE.com ", GOOD)
    assert account is not None
    assert (account["email"], account["is_admin"]) == ("boss@example.com", True)


def test_create_admin_again_resets_the_password_and_keeps_one_account(db) -> None:  # noqa: ANN001
    accounts.create_admin(db, "boss@example.com", GOOD)
    accounts.create_admin(db, "boss@example.com", "another long password")
    assert accounts.login(db, "boss@example.com", GOOD) is None
    assert accounts.login(db, "boss@example.com", "another long password") is not None
    assert db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1


def test_wrong_passwords_and_unknown_emails_fail_alike(db) -> None:  # noqa: ANN001
    accounts.create_admin(db, "boss@example.com", GOOD)
    assert accounts.login(db, "boss@example.com", "not the password") is None
    assert accounts.login(db, "nobody@example.com", GOOD) is None


def test_an_invited_account_cannot_log_in_before_it_sets_a_password(db) -> None:  # noqa: ANN001
    accounts.create_invite(db, "friend@example.com", NOW)
    assert accounts.login(db, "friend@example.com", GOOD) is None


def test_redeeming_an_invite_sets_the_password_and_the_link_works_once(db) -> None:  # noqa: ANN001
    token = accounts.create_invite(db, "Friend@Example.com", NOW)
    account = accounts.redeem_invite(db, token, GOOD, NOW + timedelta(hours=1))
    assert account["email"] == "friend@example.com"
    assert accounts.login(db, "friend@example.com", GOOD) is not None
    with pytest.raises(accounts.InviteError, match="already used"):
        accounts.redeem_invite(db, token, "a different long password", NOW)


def test_an_expired_invite_is_refused(db) -> None:  # noqa: ANN001
    token = accounts.create_invite(db, "friend@example.com", NOW)
    later = NOW + timedelta(days=accounts.INVITE_DAYS, seconds=1)
    with pytest.raises(accounts.InviteError, match="expired"):
        accounts.redeem_invite(db, token, GOOD, later)


def test_an_unknown_token_is_refused(db) -> None:  # noqa: ANN001
    with pytest.raises(accounts.InviteError, match="not valid"):
        accounts.redeem_invite(db, "nonsense", GOOD, NOW)


def test_a_short_password_is_refused_and_does_not_burn_the_invite(db) -> None:  # noqa: ANN001
    token = accounts.create_invite(db, "friend@example.com", NOW)
    with pytest.raises(accounts.InviteError, match="at least"):
        accounts.redeem_invite(db, token, "short", NOW)
    assert accounts.redeem_invite(db, token, GOOD, NOW)["email"] == "friend@example.com"


def test_issuing_a_new_link_cancels_the_old_one_and_keeps_the_account(db) -> None:  # noqa: ANN001
    first = accounts.create_invite(db, "friend@example.com", NOW)
    second = accounts.create_invite(db, "friend@example.com", NOW)
    with pytest.raises(accounts.InviteError):
        accounts.redeem_invite(db, first, GOOD, NOW)
    accounts.redeem_invite(db, second, GOOD, NOW)
    assert db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1


def test_a_new_link_for_an_existing_user_lets_them_reset_the_password(db) -> None:  # noqa: ANN001
    accounts.redeem_invite(db, accounts.create_invite(db, "f@example.com", NOW), GOOD, NOW)
    token = accounts.create_invite(db, "f@example.com", NOW)
    accounts.redeem_invite(db, token, "my brand new password", NOW)
    assert accounts.login(db, "f@example.com", GOOD) is None
    assert accounts.login(db, "f@example.com", "my brand new password") is not None


def test_a_reset_ends_the_users_existing_sessions(db) -> None:  # noqa: ANN001
    accounts.redeem_invite(db, accounts.create_invite(db, "f@example.com", NOW), GOOD, NOW)
    account = accounts.login(db, "f@example.com", GOOD)
    assert account is not None
    session = accounts.create_session(db, account["id"], NOW)
    token = accounts.create_invite(db, "f@example.com", NOW)
    accounts.redeem_invite(db, token, "my brand new password", NOW)
    assert accounts.account_for_session(db, session, NOW) is None


def test_sessions_resolve_expire_and_end(db) -> None:  # noqa: ANN001
    accounts.create_admin(db, "boss@example.com", GOOD)
    account = accounts.login(db, "boss@example.com", GOOD)
    assert account is not None
    token = accounts.create_session(db, account["id"], NOW)
    found = accounts.account_for_session(db, token, NOW + timedelta(days=1))
    assert found is not None and found["email"] == "boss@example.com"
    expired = NOW + timedelta(days=accounts.SESSION_DAYS, seconds=1)
    assert accounts.account_for_session(db, token, expired) is None
    accounts.end_session(db, token)
    assert accounts.account_for_session(db, token, NOW) is None


def test_tokens_are_stored_hashed_never_in_the_clear(db) -> None:  # noqa: ANN001
    invite = accounts.create_invite(db, "friend@example.com", NOW)
    accounts.create_admin(db, "boss@example.com", GOOD)
    account = accounts.login(db, "boss@example.com", GOOD)
    assert account is not None
    session = accounts.create_session(db, account["id"], NOW)
    stored = " ".join(
        str(v)
        for table in ("invites", "sessions")
        for row in db.execute(f"SELECT * FROM {table}")  # noqa: S608 - fixed names
        for v in tuple(row)
    )
    assert invite not in stored
    assert session not in stored


def test_listing_accounts_never_includes_hashes(db) -> None:  # noqa: ANN001
    accounts.create_admin(db, "boss@example.com", GOOD)
    accounts.create_invite(db, "friend@example.com", NOW)
    listed = accounts.list_accounts(db)
    assert [a["email"] for a in listed] == ["boss@example.com", "friend@example.com"]
    assert all("password_hash" not in a for a in listed)
    assert {a["email"]: a["has_password"] for a in listed} == {
        "boss@example.com": True,
        "friend@example.com": False,
    }
