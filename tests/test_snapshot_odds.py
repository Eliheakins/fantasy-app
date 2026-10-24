from datetime import UTC, datetime

import pytest

from fantasy.stages import snapshot_odds as so

NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)


def test_events_in_window_keeps_only_the_next_week():
    events = [
        {"id": "a", "commence_time": "2026-10-25T17:00:00Z"},
        {"id": "b", "commence_time": "2026-11-05T17:00:00Z"},
        {"id": "c", "commence_time": "2026-10-20T17:00:00Z"},
    ]
    assert [e["id"] for e in so.events_in_window(events, NOW)] == ["a"]


def test_snapshot_cost_is_one_credit_per_market_per_event():
    assert so.snapshot_cost(14) == 14 * len(so.MARKETS)


def test_api_key_reads_env_file_and_fails_loudly_without_one(tmp_path, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    env = tmp_path / ".env"
    with pytest.raises(RuntimeError, match="ODDS_API_KEY"):
        so.api_key(env)
    env.write_text("ODDS_API_KEY=abc123\n")
    assert so.api_key(env) == "abc123"


def test_log_credits_writes_header_once(tmp_path):
    so.log_credits("s1", "6", "494", tmp_path)
    so.log_credits("s2", "12", "488", tmp_path)
    lines = (tmp_path / "credit_log.csv").read_text().splitlines()
    assert lines == [
        "snapshot,credits_used_total,credits_remaining",
        "s1,6,494",
        "s2,12,488",
    ]


def test_a_failed_request_does_not_expose_the_api_key(monkeypatch):
    monkeypatch.setattr(so.httpx, "get", lambda *a, **k: so.httpx.Response(401))
    with pytest.raises(RuntimeError) as err:
        so._get(f"{so.BASE}/events", {"apiKey": "SECRET"})
    assert "SECRET" not in str(err.value) and "401" in str(err.value)


def test_env_parser_handles_quotes_export_and_comments(tmp_path, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("# ODDS_API_KEY=old\nOTHER=1\nexport ODDS_API_KEY='abc 123'\n")
    assert so.api_key(env) == "abc 123"
    env.write_text('ODDS_API_KEY="k#1"\n')
    assert so.api_key(env) == "k#1"
