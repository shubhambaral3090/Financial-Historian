from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from financial_historian.market import BoundedMarketCache, YahooFinanceProvider
from financial_historian.yahoo_access import YahooAccessCooldown, YahooRequestGate


class Clock:
    def __init__(self):
        self.current = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

    def __call__(self):
        return self.current

    def advance(self, seconds):
        self.current += timedelta(seconds=seconds)

    def seconds(self):
        return self.current.timestamp()


def frame(*values, dates=None):
    dates = dates or [f"2026-01-{n:02}" for n in range(1, len(values) + 1)]
    return pd.DataFrame({"Close": values}, index=pd.DatetimeIndex(dates, tz="America/New_York"))


def provider(downloader, *, clock=None, **kwargs):
    clock = clock or Clock()
    gate = kwargs.pop("gate", YahooRequestGate(0, clock=clock.seconds))
    return YahooFinanceProvider(downloader=downloader, clock=clock, gate=gate, **kwargs)


def test_yahoo_adapter_returns_latest_close_and_change_with_source_timestamp():
    calls = []
    service = provider(lambda *args, **kwargs: calls.append((args, kwargs)) or (frame(100, 103), {"currency": "USD"}))
    quote = service.quote("AAPL")
    assert quote.price == 103
    assert quote.change == 3
    assert quote.change_percent == 3
    assert quote.status == "latest available close"
    assert quote.delayed
    assert quote.source == "Yahoo Finance"
    assert quote.retrieved_at == "2026-10-08T12:00:00+00:00"
    assert quote.checked_at == quote.retrieved_at
    assert quote.as_of == "2026-01-02"
    assert quote.timezone == "America/New_York"
    assert quote.currency == "USD"
    assert calls[0][0] == ("AAPL",)
    assert calls[0][1]["timeout"] == 10


def test_current_daily_bar_is_not_presented_as_a_final_close():
    quote = provider(lambda *args, **kwargs: frame(100, 103, dates=["2026-10-07", "2026-10-08"])).quote("AAPL")
    assert quote.status == "delayed daily price"
    assert quote.as_of == "2026-10-08"
    assert quote.currency == ""  # Never assume every Yahoo instrument trades in USD.


def test_yahoo_adapter_caches_and_bounds_requests():
    calls = []
    cache = BoundedMarketCache(max_entries=1)
    service = provider(lambda *args, **kwargs: calls.append(1) or frame(1, 2), cache=cache)
    original = service.quote("AAA")
    cached = service.quote("AAA")
    assert cached.cached and not cached.stale
    assert cached.retrieved_at == original.retrieved_at
    service.quote("BBB")
    service.quote("AAA")
    assert len(calls) == 3  # Oldest success is evicted, not archived.


def test_force_refresh_and_expired_cache_check_provider_again():
    calls = []
    clock = Clock()
    service = provider(lambda *args, **kwargs: calls.append(1) or frame(1, len(calls) + 1), clock=clock)
    assert service.quote("AAA").price == 2
    assert service.quote("AAA").price == 2
    clock.advance(1)
    assert service.quote("AAA", force_refresh=True).price == 3
    clock.advance(301)
    assert service.quote("AAA").price == 4
    assert len(calls) == 3


@pytest.mark.parametrize(("exception", "message"), [
    (TimeoutError("private diagnostic timeout for user@private.test"), "did not respond in time"),
    (RuntimeError("HTTP Error 403: Forbidden private-request-url"), "declined this request"),
    (RuntimeError("HTTP 429 request limited private-request-url"), "limiting requests"),
    (ValueError("private malformed payload"), "usable market data"),
    (RuntimeError("private network credentials"), "temporarily unavailable"),
])
def test_provider_failure_is_safe_nonfatal_and_not_repeated_during_cooldown(exception, message):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise exception
    service = provider(fail)
    quote = service.quote("AAPL")
    assert quote.price is None
    assert quote.status == "unavailable"
    assert message in quote.error
    assert "private" not in quote.error
    assert quote.retrieved_at == ""  # Failed attempts are not successful data retrievals.
    assert quote.checked_at
    service.quote("AAPL", force_refresh=True)
    assert calls == [1]


def test_failed_refresh_keeps_last_good_quote_and_original_timestamps():
    clock = Clock()
    calls = []
    def download(*args, **kwargs):
        calls.append(1)
        if len(calls) > 1:
            raise TimeoutError("timeout")
        return frame(10, 12)
    service = provider(download, clock=clock)
    original = service.quote("AAPL")
    clock.advance(301)
    stale = service.quote("AAPL", force_refresh=True)
    assert stale.price == 12 and stale.history == original.history
    assert stale.stale and stale.cached
    assert stale.retrieved_at == original.retrieved_at
    assert stale.as_of == original.as_of
    assert stale.checked_at != original.checked_at
    assert stale.error
    assert service.cache.get(("AAPL", "1y"), clock.seconds(), 86400) == original


def test_last_good_fallback_expires_and_recovery_replaces_only_after_success():
    clock = Clock()
    fail = False
    def download(*args, **kwargs):
        if fail:
            raise TimeoutError("timeout")
        return frame(10, 12)
    service = provider(download, clock=clock, max_stale_seconds=600)
    service.quote("AAPL")
    fail = True
    clock.advance(601)
    assert service.quote("AAPL").price is None
    fail = False
    clock.advance(61)
    recovered = service.quote("AAPL")
    assert recovered.price == 12 and not recovered.stale and not recovered.error


def test_failed_forced_check_does_not_relabel_a_valid_cached_quote_as_fresh():
    clock = Clock()
    calls = []
    def download(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise TimeoutError("timeout")
        return frame(10, 12)
    service = provider(download, clock=clock)
    service.quote("AAPL")
    clock.advance(1)
    assert service.quote("AAPL", force_refresh=True).stale
    assert service.quote("AAPL").stale
    clock.advance(61)
    assert not service.quote("AAPL").stale
    assert len(calls) == 3  # Known failed checks retry after cooldown, even within TTL.


@pytest.mark.parametrize("bad_frame", [None, object(), frame(), frame(float("nan"), float("inf"), -1, 0)])
def test_empty_or_malformed_history_has_no_invented_price(bad_frame):
    quote = provider(lambda *args, **kwargs: bad_frame).quote("AAPL")
    assert quote.price is None
    assert quote.history == ()
    assert quote.error


def test_invalid_values_do_not_corrupt_valid_prices_and_dates_are_sorted_deduplicated():
    quote = provider(lambda *args, **kwargs: frame(12, 10, float("inf"), 11, 13,
        dates=["2026-01-02", "2026-01-01", "2026-01-03", "2026-01-01", "2026-01-02"])).quote("AAPL")
    assert [(point.timestamp, point.close) for point in quote.history] == [("2026-01-01", 11), ("2026-01-02", 13)]
    assert quote.price == 13
    assert quote.change == 2


def test_multi_ticker_frame_selects_exact_requested_symbol():
    data = pd.DataFrame([[10, 100], [12, 105]], index=pd.date_range("2026-01-01", periods=2),
                        columns=pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Close", "MSFT")]))
    service = provider(lambda *args, **kwargs: data)
    assert service.quote("MSFT").price == 105
    assert service.quote("AAPL").price == 12
    assert service.quote("GOOGL").price is None


def test_single_point_history_keeps_price_without_inventing_daily_movement():
    quote = provider(lambda *args, **kwargs: frame(10)).quote("AAPL")
    assert quote.price == 10
    assert quote.change is None and quote.change_percent is None
    assert len(quote.history) == 1  # UI can show a no-chart fallback for one point.


@pytest.mark.parametrize("symbol", ["", "AAPL/evil", "=formula()", "<script>", "A" * 30])
def test_invalid_symbols_do_not_reach_yahoo(symbol):
    calls = []
    quote = provider(lambda *args, **kwargs: calls.append(1)).quote(symbol)
    assert not calls
    assert quote.price is None


def test_class_share_symbol_is_normalized_only_for_yahoo():
    calls = []
    quote = provider(lambda symbol, **kwargs: calls.append(symbol) or frame(10, 11)).quote("brk.b")
    assert calls == ["BRK-B"]
    assert quote.ticker == "BRK-B"


def test_parallel_quote_misses_are_coalesced():
    calls = []
    service = provider(lambda *args, **kwargs: calls.append(1) or frame(10, 11))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.quote("AAPL"), range(4)))
    assert len(calls) == 1
    assert all(result.price == 11 for result in results)


def test_shared_gate_paces_requests_and_rate_limits_across_providers():
    clock = Clock()
    sleeps = []
    def sleep(seconds):
        sleeps.append(seconds)
        clock.advance(seconds)
    gate = YahooRequestGate(0.5, clock=clock.seconds, sleep=sleep)
    assert gate.run(lambda: "universe") == "universe"
    assert gate.run(lambda: "quote") == "quote"
    assert sleeps == [0.5]
    def fail():
        raise RuntimeError("429")
    with pytest.raises(RuntimeError):
        gate.run(fail)
    with pytest.raises(YahooAccessCooldown) as caught:
        gate.run(lambda: "never called")
    assert caught.value.kind == "rate_limit"
    clock.advance(61)
    assert gate.run(lambda: "recovered") == "recovered"


def test_failure_cache_is_bounded_independently_of_success_cache():
    service = provider(lambda *args, **kwargs: frame(), cache=BoundedMarketCache(max_entries=2))
    for symbol in ("AAA", "BBB", "CCC"):
        service.quote(symbol)
    assert len(service._failures) == 2


def test_native_yfinance_adapter_uses_public_history_and_tolerates_metadata_failure(monkeypatch):
    import yfinance as yf
    calls = []
    class Ticker:
        def __init__(self, symbol, *, session):
            calls.append((symbol, session))

        def history(self, **kwargs):
            calls.append(kwargs)
            return frame(10, 12)

        def get_history_metadata(self):
            raise TimeoutError("metadata unavailable")
    monkeypatch.setattr(yf, "Ticker", Ticker)
    service = YahooFinanceProvider(clock=Clock(), gate=YahooRequestGate(0))
    quote = service.quote("AAPL")
    assert quote.price == 12
    assert quote.currency == ""
    assert calls[0][0] == "AAPL" and calls[0][1] is not None
    assert calls[1]["raise_errors"] is True
    assert calls[1]["auto_adjust"] is False
    assert calls[1]["timeout"] == 10


@pytest.mark.parametrize("requested", [None, 120, (30, 30), 0, 2])
def test_shared_yahoo_session_clamps_timeout_without_disabling_tls(monkeypatch, requested):
    from curl_cffi.requests import Session
    from financial_historian import yahoo_access
    calls = []
    monkeypatch.setattr(yahoo_access, "_SESSION", None)
    monkeypatch.setattr(Session, "request", lambda self, method, url, **kwargs: calls.append(kwargs))
    session = yahoo_access.yahoo_session()
    try:
        session.request("GET", "https://query1.finance.yahoo.com/fixture", timeout=requested)
        assert calls[0]["timeout"] == (2 if requested == 2 else 10)
        assert calls[0].get("verify", True) is True
    finally:
        session.close()
