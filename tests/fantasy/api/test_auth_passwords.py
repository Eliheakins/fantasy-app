import threading
import time

import pytest

from fantasy.auth import passwords


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real cost (128 MiB, a third of a second) is for production, not for every test."""
    monkeypatch.setattr(passwords, "COST_N", 2**10)


def test_a_password_verifies_against_its_own_hash() -> None:
    stored = passwords.hash_password("correct horse battery")
    assert passwords.verify_password("correct horse battery", stored)


def test_a_wrong_password_does_not_verify() -> None:
    stored = passwords.hash_password("correct horse battery")
    assert not passwords.verify_password("correct horse batterz", stored)
    assert not passwords.verify_password("", stored)


def test_two_hashes_of_one_password_differ_because_of_the_salt() -> None:
    assert passwords.hash_password("same password here") != passwords.hash_password(
        "same password here"
    )


def test_the_hash_remembers_its_cost_so_older_hashes_still_verify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = passwords.hash_password("remember my cost please")
    monkeypatch.setattr(passwords, "COST_N", 2**12)  # the setting moves on
    assert passwords.verify_password("remember my cost please", stored)


@pytest.mark.parametrize("junk", ["", "plain", "scrypt$x$y", "scrypt$1024$8$1$!!$!!", "md5$a$b"])
def test_a_malformed_stored_value_never_verifies_and_never_raises(junk: str) -> None:
    assert not passwords.verify_password("anything at all", junk)


def test_the_dummy_check_runs_a_full_hash_for_unknown_accounts() -> None:
    assert passwords.verify_password("anything at all", passwords.dummy_hash()) is False


def test_at_most_two_hashes_run_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    running = 0
    peak = 0
    lock = threading.Lock()
    real = passwords._scrypt

    def slow(*args: object, **kwargs: object) -> bytes:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(passwords, "_scrypt", slow)
    threads = [threading.Thread(target=passwords.hash_password, args=("x" * 12,)) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak <= passwords.MAX_CONCURRENT_HASHES


def test_the_length_rules() -> None:
    assert passwords.check_length("a" * passwords.MIN_PASSWORD_LENGTH) is None
    assert "at least" in (passwords.check_length("short") or "")
    assert "at most" in (passwords.check_length("a" * (passwords.MAX_PASSWORD_LENGTH + 1)) or "")
