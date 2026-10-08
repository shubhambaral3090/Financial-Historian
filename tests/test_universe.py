"""Yahoo suggestions are bounded, cacheable and never substitute for SEC identity."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import random

import pytest

from financial_historian.universe import (
    CONFIG_ENV, DEFAULT_GROUPS, INDEX_LIMITATION, SOURCE, MANUAL_SOURCE, MANUAL_STATUS,
    InvalidScreenerResponse, ScreenerGroup, UniverseConfigError,
    UniverseProvider, ManualUniverseProvider, load_screener_groups, parse_predefined_screener,
    parse_ticker_groups,
    shuffled_suggestions,
)


NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
GROUP = ScreenerGroup("most_actives", "Most active stocks")


class Clock:
    def __init__(self):
        self.value = NOW

    def __call__(self):
        return self.value

    def advance(self, **kwargs):
        self.value += timedelta(**kwargs)


def response(*symbols, screen="most_actives"):
    return {
        "canonicalName": screen.upper(),
        "quotes": [{"symbol": symbol, "longName": f"{symbol} Incorporated", "quoteType": "EQUITY"} for symbol in symbols],
    }


class Fetcher:
    def __init__(self, data=None):
        self.data = data or response("AAA", "BBB", "CCC", "DDD")
        self.calls = []
        self.error = None

    def __call__(self, screen, *, count):
        self.calls.append((screen, count))
        if self.error is not None:
            raise self.error
        return self.data


def provider(fetch=None, clock=None, **kwargs):
    return UniverseProvider(fetch or Fetcher(), groups=(GROUP,), clock=clock or Clock(), **kwargs)


def test_actual_default_screen_ids_do_not_claim_index_membership():
    from yfinance import PREDEFINED_SCREENER_QUERIES
    assert all(group.screener_id in PREDEFINED_SCREENER_QUERIES for group in DEFAULT_GROUPS)
    assert all(not group.indexes and not group.membership_verified for group in DEFAULT_GROUPS)
    result = provider().load()
    assert result.members
    assert result.source == SOURCE
    assert INDEX_LIMITATION in result.warnings
    assert all(not member.indexes for member in result.members)


def test_parse_yfinance_response_does_not_trust_yahoo_cik():
    payload = response("BRK-B")
    payload["quotes"][0]["cik"] = "123"
    payload["quotes"][0]["longName"] = "  Berkshire\n Hathaway  "
    members = parse_predefined_screener(payload, group=GROUP, retrieved_at=NOW.isoformat())
    assert len(members) == 1
    assert members[0].company.ticker == "BRK-B"
    assert members[0].company.cik == ""
    assert members[0].company.name == "Berkshire Hathaway"
    assert members[0].source_url.startswith("https://query1.finance.yahoo.com/")
    assert members[0].retrieved_at == NOW.isoformat()


def test_parse_original_envelope_and_filter_invalid_non_equity_records():
    payload = response("ABC")
    payload["quotes"] += [
        {"symbol": "^NDX", "shortName": "Index", "quoteType": "INDEX"},
        {"symbol": "QQQ", "shortName": "ETF", "quoteType": "ETF"},
        {"symbol": "BAD<TAG>", "shortName": "Unsafe symbol"},
        {"symbol": "NO_NAME"}, "not a quote", {"symbol": 123, "shortName": "Not a symbol"},
    ]
    members = parse_predefined_screener(
        {"finance": {"result": [payload], "error": None}}, group=GROUP, retrieved_at=NOW.isoformat(),
    )
    assert [member.company.ticker for member in members] == ["ABC"]


@pytest.mark.parametrize("payload", [
    None, [], {}, {"quotes": []}, {"quotes": "wrong type"},
    {"quotes": [{"symbol": "ABC"}]},
    {"finance": {"result": [], "error": None}},
    {"finance": {"result": [response("ABC")], "error": {"code": "Forbidden"}}},
    response("ABC", screen="wrong_screen"),
    {"quotes": [{"symbol": "ABC", "longName": "Example"}] * 251},
])
def test_malformed_or_wrong_screen_payload_is_rejected(payload):
    with pytest.raises(InvalidScreenerResponse):
        parse_predefined_screener(payload, group=GROUP, retrieved_at=NOW.isoformat())


def test_duplicate_index_membership_preserves_both_sources():
    # These are explicitly certified test-only group IDs, not claimed Yahoo IDs.
    groups = (
        ScreenerGroup("fixture_sp500", "Verified S&P fixture", ("S&P 500",), True),
        ScreenerGroup("fixture_nasdaq100", "Verified Nasdaq fixture", ("Nasdaq-100",), True),
    )
    def fetch(screen, *, count):
        return response("ABC", "XYZ" if screen == "fixture_sp500" else "ABC", screen=screen)
    result = UniverseProvider(fetch, groups=groups, clock=Clock()).load()
    member = next(member for member in result.members if member.company.ticker == "ABC")
    assert len(result.members) == 2
    assert member.indexes == ("Nasdaq-100", "S&P 500")
    assert len(member.source_urls) == 2
    assert len(member.groups) == 2
    assert member.company.cik == ""
    assert INDEX_LIMITATION not in result.warnings


def test_unverified_configured_index_is_not_presented_as_membership():
    group = ScreenerGroup("most_actives", "General screen", ("S&P 500",))
    result = UniverseProvider(Fetcher(), groups=(group,), clock=Clock()).load()
    assert all(not member.indexes for member in result.members)
    assert INDEX_LIMITATION in result.warnings


def test_capped_screen_count_is_explicit_not_a_complete_index_claim():
    fetch = Fetcher(response("AAA", "BBB"))
    fetch.data["total"] = 503
    source = provider(fetch)
    result = source.load()
    assert len(result.members) == 2
    assert any("2 returned stock suggestions out of 503" in warning for warning in result.warnings)
    assert source.load().warnings == result.warnings


def test_verified_group_without_total_still_discloses_membership_completeness():
    group = ScreenerGroup("fixture_index", "Index fixture", ("S&P 500",), True)
    result = UniverseProvider(Fetcher(response("AAA", screen="fixture_index")), groups=(group,), clock=Clock()).load()
    assert any("did not confirm a complete constituent count" in warning for warning in result.warnings)


def test_local_shuffling_never_requests_again_or_mutates_cached_order():
    fetch = Fetcher()
    source = provider(fetch)
    snapshot = source.load()
    original = snapshot.members
    first = shuffled_suggestions(snapshot, limit=4, rng=random.Random(1))
    second = shuffled_suggestions(snapshot, limit=4, rng=random.Random(2))
    assert first != second
    assert set(first) == set(second) == set(original)
    assert snapshot.members == original
    assert len(fetch.calls) == 1
    assert shuffled_suggestions(source.load(), limit=2, rng=random.Random(3))
    assert len(fetch.calls) == 1
    assert shuffled_suggestions(snapshot, limit=0) == ()


def test_successful_lists_use_twelve_hour_ttl_and_preserve_retrieval_timestamp():
    fetch, clock = Fetcher(), Clock()
    source = provider(fetch, clock)
    first = source.load()
    clock.advance(hours=11)
    cached = source.load()
    assert cached.retrieved_at == first.retrieved_at
    assert cached.checked_at != first.checked_at
    assert len(fetch.calls) == 1
    assert not cached.stale
    clock.advance(hours=1)
    updated = source.load()
    assert len(fetch.calls) == 2
    assert updated.retrieved_at != first.retrieved_at


class HttpFailure(Exception):
    def __init__(self, code):
        self.response = type("Response", (), {"status_code": code})()
        super().__init__(f"HTTP {code}: private upstream diagnostic must not escape")


@pytest.mark.parametrize("failure", [HttpFailure(403), HttpFailure(429), TimeoutError("private timeout detail")])
def test_failure_keeps_last_good_timestamp_and_observes_retry_cooldown(failure):
    fetch, clock = Fetcher(), Clock()
    source = provider(fetch, clock)
    original = source.load()
    assert original.members
    clock.advance(hours=13)
    fetch.error = failure
    fallback = source.load()
    assert fallback.members == original.members
    assert fallback.retrieved_at == original.retrieved_at
    assert fallback.stale
    assert any("last successful list" in warning for warning in fallback.warnings)
    assert all("private" not in warning for warning in fallback.warnings)
    source.load()
    assert len(fetch.calls) == 2
    clock.advance(seconds=301)
    fetch.error = None
    recovered = source.load()
    assert len(fetch.calls) == 3
    assert not recovered.stale
    assert recovered.retrieved_at == clock.value.isoformat()


def test_malformed_refresh_never_overwrites_last_good_list():
    fetch, clock = Fetcher(), Clock()
    source = provider(fetch, clock)
    original = source.load()
    assert original.members
    clock.advance(hours=13)
    fetch.data = {"quotes": []}
    failed = source.load()
    assert failed.members == original.members
    assert failed.retrieved_at == original.retrieved_at
    assert failed.stale
    assert any("unrecognized" in warning for warning in failed.warnings)


def test_cold_failure_is_nonfatal_and_no_result_is_implied_current():
    fetch = Fetcher()
    fetch.error = HttpFailure(403)
    result = provider(fetch).load()
    assert result.members == ()
    assert result.retrieved_at == ""
    assert any("Direct SEC company search remains available" in warning for warning in result.warnings)


def test_last_good_is_evicted_after_seven_days_not_kept_as_archive():
    fetch, clock = Fetcher(), Clock()
    source = provider(fetch, clock)
    source.load()
    clock.advance(days=7)
    fetch.error = TimeoutError()
    result = source.load()
    assert not result.members
    assert not result.retrieved_at
    assert not source._provider._entries


def test_partial_failure_keeps_successful_group_available():
    groups = (GROUP, ScreenerGroup("day_gainers", "Daily gainers"))
    def fetch(screen, *, count):
        if screen == "day_gainers":
            raise HttpFailure(429)
        return response("ABC", screen=screen)
    result = UniverseProvider(fetch, groups=groups, clock=Clock()).load()
    assert [member.company.ticker for member in result.members] == ["ABC"]
    assert result.group_timestamps == ((GROUP.label, NOW.isoformat()),)
    assert any("Daily gainers" in warning for warning in result.warnings)


def test_concurrent_loads_coalesce_successful_requests():
    fetch = Fetcher()
    source = provider(fetch)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: source.load(), range(8)))
    assert len(fetch.calls) == 1
    assert all(result.members == results[0].members for result in results)


def test_groups_are_configurable_without_spreading_screen_ids(monkeypatch):
    config = json.dumps([{"id": "growth_technology_stocks", "label": "Technology"}])
    monkeypatch.setenv(CONFIG_ENV, config)
    assert load_screener_groups() == (ScreenerGroup("growth_technology_stocks", "Technology"),)
    assert load_screener_groups("") == DEFAULT_GROUPS


@pytest.mark.parametrize("config", [
    "private invalid JSON", "{}", "[]", '[{"id":"https://example.invalid"}]',
    '[{"id":"most_actives","indexes":"S&P 500"}]',
    '[{"id":"most_actives","indexes":["Unknown"]}]',
    '[{"id":"most_actives","membership_verified":"yes"}]',
    '[{"id":"most_actives"},{"id":"most_actives"}]',
    '[{"id":"most_actives","url":"https://example.invalid"}]',
])
def test_bad_configuration_has_safe_errors(config):
    with pytest.raises(UniverseConfigError) as caught:
        load_screener_groups(config)
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("ttl", [1, 6 * 3600 - 1, 24 * 3600 + 1])
def test_universe_ttl_is_bounded(ttl):
    with pytest.raises(ValueError):
        provider(ttl_seconds=ttl)


def test_default_fetch_uses_yfinance_predefined_api_and_shared_gate(monkeypatch):
    import yfinance
    from financial_historian import yahoo_access
    calls = []
    class Gate:
        def run(self, action):
            calls.append("gate")
            return action()
    session = object()
    monkeypatch.setattr(yahoo_access, "yahoo_request_gate", lambda: Gate())
    monkeypatch.setattr(yahoo_access, "yahoo_session", lambda: session)
    def screen(screener_id, *, count, session):
        calls.append((screener_id, count, session))
        return response("ABC", screen=screener_id)
    monkeypatch.setattr(yfinance, "screen", screen)
    result = UniverseProvider(groups=(GROUP,), clock=Clock()).load()
    assert result.members[0].company.ticker == "ABC"
    assert calls == ["gate", ("most_actives", 250, session)]


def manual_payload():
    return {
        "schema_version": 1, "maintained_at": "2026-10-08",
        "groups": [
            {"name": "S&P 500", "complete": False, "tickers": [{"symbol": "ABC", "name": "Example"}]},
            {"name": "Nasdaq-100", "complete": False, "tickers": [{"symbol": "ABC", "name": "Example"}]},
        ],
    }


def test_default_approved_manual_configuration_never_requests_yahoo(monkeypatch):
    import yfinance
    monkeypatch.delenv(CONFIG_ENV, raising=False)
    def no_network(*args, **kwargs):
        pytest.fail("Manual ticker groups must not fetch Yahoo membership")
    monkeypatch.setattr(yfinance, "screen", no_network)
    source = UniverseProvider(clock=Clock())
    result = source.load()
    assert result.origin == "manual_ticker_groups"
    assert result.source == MANUAL_SOURCE
    assert result.membership_status == MANUAL_STATUS
    assert result.maintained_at == "2026-10-07"
    assert result.retrieved_at == ""
    assert len(result.members) >= 30
    assert any("incomplete starter group" in warning for warning in result.warnings)
    assert any("not independently verified" in warning for warning in result.warnings)
    assert all(member.company.cik == "" for member in result.members)
    assert all(member.retrieved_at == "" and not member.source_url for member in result.members)
    first = shuffled_suggestions(result, rng=random.Random(1))
    second = shuffled_suggestions(source.load(), rng=random.Random(2))
    assert first != second


def test_manual_duplicate_membership_is_configured_not_verified():
    result = parse_ticker_groups(manual_payload(), checked_at=NOW.isoformat())
    assert len(result.members) == 1
    assert result.members[0].indexes == ("Nasdaq-100", "S&P 500")
    assert result.members[0].membership_status == MANUAL_STATUS
    assert result.maintained_at != result.checked_at
    assert not result.retrieved_at


@pytest.mark.parametrize("change", [
    {"schema_version": 0}, {"maintained_at": "not a date"}, {"maintained_at": None},
    {"groups": []}, {"groups": [{"name": "Dow Jones", "tickers": []}]},
    {"groups": [{"name": "S&P 500", "tickers": [{"symbol": "BAD<TAG>", "name": "Bad"}]}]},
    {"groups": [{"name": "S&P 500", "tickers": [{"symbol": "AAA"}]}]},
    {"groups": [{"name": "S&P 500", "complete": "yes", "tickers": [{"symbol": "AAA", "name": "A"}]}]},
])
def test_manual_configuration_validation_is_strict(change):
    payload = manual_payload()
    payload.update(change)
    with pytest.raises(UniverseConfigError):
        parse_ticker_groups(payload, checked_at=NOW.isoformat())


def test_missing_manual_configuration_is_nonfatal(tmp_path):
    result = UniverseProvider(config_path=tmp_path / "missing.json", clock=Clock()).load()
    assert result.members == ()
    assert result.origin == "manual_ticker_groups"
    assert result.maintained_at == result.retrieved_at == ""
    assert any("Direct SEC company search remains available" in warning for warning in result.warnings)


def test_manual_configuration_retains_last_good_on_corruption(monkeypatch):
    from pathlib import Path
    source = ManualUniverseProvider(clock=Clock())
    original = source.load()
    original_stat = Path.stat
    def changed_stat(path, *args, **kwargs):
        stat = original_stat(path, *args, **kwargs)
        return type("ChangedStat", (), {"st_mtime_ns": stat.st_mtime_ns + 1, "st_size": stat.st_size})()
    monkeypatch.setattr(Path, "stat", changed_stat)
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: "{private broken input")
    fallback = source.load()
    assert fallback.members == original.members
    assert fallback.stale
    assert fallback.maintained_at == original.maintained_at
    assert not fallback.retrieved_at
    assert all("private broken" not in warning for warning in fallback.warnings)


def test_optional_yahoo_config_switches_from_manual_mode(monkeypatch):
    monkeypatch.setenv(CONFIG_ENV, '[{"id":"most_actives","label":"Most active"}]')
    source = UniverseProvider(clock=Clock())
    source._provider.fetch_screen = Fetcher()
    result = source.load()
    assert result.origin == "yahoo_screeners"
    assert result.retrieved_at == NOW.isoformat()
    assert result.maintained_at == ""
    assert result.source == SOURCE
