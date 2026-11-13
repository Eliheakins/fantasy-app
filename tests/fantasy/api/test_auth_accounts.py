from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auth_fixture import GOOD

from fantasy.auth import accounts, passwords

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "COST_N", 2**10)


@pytest.fixture
def db(tmp_path: Path):
    conn = accounts.connect(tmp_path)
    yield conn
    conn.close()


def test_an_admin_can_log_in_with_any_email_casing(db) -> None:
    accounts.create_admin(db, "Boss@Example.com", GOOD)
    account = accounts.login(db, "  boss@EXAMPLE.com ", GOOD)
    assert account is not None
    assert (account["email"], account["is_admin"]) == ("boss@example.com", True)


def test_create_admin_again_resets_the_password_and_keeps_one_account(db) -> None:
    accounts.create_admin(db, "boss@example.com", GOOD)
    accounts.create_admin(db, "boss@example.com", "another long password")
    assert accounts.login(db, "boss@example.com", GOOD) is None
    assert accounts.login(db, "boss@example.com", "another long password") is not None
    assert db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1


def test_wrong_passwords_and_unknown_emails_fail_alike(db) -> None:
    accounts.create_admin(db, "boss@example.com", GOOD)
    assert accounts.login(db, "boss@example.com", "not the password") is None
    assert accounts.login(db, "nobody@example.com", GOOD) is None


def test_an_invited_account_cannot_log_in_before_it_sets_a_password(db) -> None:
    accounts.create_invite(db, "friend@example.com", NOW)
    assert accounts.login(db, "friend@example.com", GOOD) is None


def test_redeeming_an_invite_sets_the_password_and_the_link_works_once(db) -> None:
    token = accounts.create_invite(db, "Friend@Example.com", NOW)
    account = accounts.redeem_invite(db, token, GOOD, NOW + timedelta(hours=1))
    assert account["email"] == "friend@example.com"
    assert accounts.login(db, "friend@example.com", GOOD) is not None
    with pytest.raises(accounts.InviteError, match="already used"):
        accounts.redeem_invite(db, token, "a different long password", NOW)


def test_an_expired_invite_is_refused(db) -> None:
    token = accounts.create_invite(db, "friend@example.com", NOW)
    later = NOW + timedelta(days=accounts.INVITE_DAYS, seconds=1)
    with pytest.raises(accounts.InviteError, match="expired"):
        accounts.redeem_invite(db, token, GOOD, later)


def test_an_unknown_token_is_refused(db) -> None:
    with pytest.raises(accounts.InviteError, match="not valid"):
        accounts.redeem_invite(db, "nonsense", GOOD, NOW)


def test_a_short_password_is_refused_and_does_not_burn_the_invite(db) -> None:
    token = accounts.create_invite(db, "friend@example.com", NOW)
    with pytest.raises(accounts.InviteError, match="at least"):
        accounts.redeem_invite(db, token, "short", NOW)
    assert accounts.redeem_invite(db, token, GOOD, NOW)["email"] == "friend@example.com"


def test_issuing_a_new_link_cancels_the_old_one_and_keeps_the_account(db) -> None:
    first = accounts.create_invite(db, "friend@example.com", NOW)
    second = accounts.create_invite(db, "friend@example.com", NOW)
    with pytest.raises(accounts.InviteError):
        accounts.redeem_invite(db, first, GOOD, NOW)
    accounts.redeem_invite(db, second, GOOD, NOW)
    assert db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1


def test_a_new_link_for_an_existing_user_lets_them_reset_the_password(db) -> None:
    accounts.redeem_invite(db, accounts.create_invite(db, "f@example.com", NOW), GOOD, NOW)
    token = accounts.create_invite(db, "f@example.com", NOW)
    accounts.redeem_invite(db, token, "my brand new password", NOW)
    assert accounts.login(db, "f@example.com", GOOD) is None
    assert accounts.login(db, "f@example.com", "my brand new password") is not None


def test_a_reset_ends_the_users_existing_sessions(db) -> None:
    accounts.redeem_invite(db, accounts.create_invite(db, "f@example.com", NOW), GOOD, NOW)
    account = accounts.login(db, "f@example.com", GOOD)
    assert account is not None
    session = accounts.create_session(db, account["id"], NOW)
    token = accounts.create_invite(db, "f@example.com", NOW)
    accounts.redeem_invite(db, token, "my brand new password", NOW)
    assert accounts.account_for_session(db, session, NOW) is None


def test_sessions_resolve_expire_and_end(db) -> None:
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


def test_tokens_are_stored_hashed_never_in_the_clear(db) -> None:
    invite = accounts.create_invite(db, "friend@example.com", NOW)
    accounts.create_admin(db, "boss@example.com", GOOD)
    account = accounts.login(db, "boss@example.com", GOOD)
    assert account is not None
    session = accounts.create_session(db, account["id"], NOW)
    stored = " ".join(
        str(v)
        for table in ("invites", "sessions")
        for row in db.execute(f"SELECT * FROM {table}")
        for v in tuple(row)
    )
    assert invite not in stored
    assert session not in stored


def test_listing_accounts_never_includes_hashes(db) -> None:
    accounts.create_admin(db, "boss@example.com", GOOD)
    accounts.create_invite(db, "friend@example.com", NOW)
    listed = accounts.list_accounts(db, NOW)
    assert [a["email"] for a in listed] == ["boss@example.com", "friend@example.com"]
    assert all("password_hash" not in a for a in listed)
    assert {a["email"]: a["has_password"] for a in listed} == {
        "boss@example.com": True,
        "friend@example.com": False,
    }


def test_an_expired_unused_invite_is_not_listed_as_pending(db) -> None:
    accounts.create_invite(db, "old@example.com", NOW - timedelta(days=accounts.INVITE_DAYS + 1))
    accounts.create_invite(db, "new@example.com", NOW)
    listed = accounts.list_accounts(db, NOW)
    assert {a["email"]: a["invite_pending"] for a in listed} == {
        "old@example.com": False,
        "new@example.com": True,
    }


def test_a_new_auth_db_and_its_wal_files_are_owner_only(tmp_path: Path) -> None:
    data_dir = tmp_path / "fresh" / "data"
    conn = accounts.connect(data_dir)
    try:
        accounts.create_admin(conn, "boss@example.com", GOOD)
        files = [accounts.db_path(data_dir), *data_dir.glob("auth.db-*")]
        assert {f.name for f in files} >= {"auth.db", "auth.db-wal", "auth.db-shm"}
        assert [oct(f.stat().st_mode & 0o777) for f in files] == ["0o600"] * len(files)
        assert oct(data_dir.stat().st_mode & 0o777) == "0o700"
    finally:
        conn.close()


def test_a_db_file_owned_by_another_user_still_opens_with_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def refuse(self: Path, mode: int) -> None:
        raise PermissionError(f"not the owner of {self}")

    monkeypatch.setattr(Path, "chmod", refuse)
    conn = accounts.connect(tmp_path)
    try:
        assert conn.execute("SELECT count(*) FROM accounts").fetchone()[0] == 0
    finally:
        conn.close()
    assert "cannot make" in caplog.text
