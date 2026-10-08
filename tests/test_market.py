from datetime import datetime, timezone

from financial_historian.market import BoundedMarketCache, YahooFinanceProvider


class Row:
    def __init__(self, close):
        self.data = {"Close": close}

    def iterrows(self):
        for day, value in (("2026-01-01", 100), ("2026-01-02", 103)):
            yield type("Index", (), {"date": lambda self, d=day: d})(), RowValue(value)


class RowValue:
    def __init__(self, value):
        self.value = value

    def __getitem__(self, key):
        return self.value


def frame(*values):
    class Frame:
        def iterrows(self):
            for index, value in enumerate(values, 1):
                yield type("Index", (), {"date": lambda self, n=index: f"2026-01-0{n}"})(), {"Close": value}
    return Frame()


def test_yahoo_adapter_returns_latest_close_and_change_with_source_timestamp():
    calls = []
    provider = YahooFinanceProvider(
        downloader=lambda *args, **kwargs: calls.append((args, kwargs)) or frame(100, 103),
        clock=lambda: datetime(2026, 10, 8, 12, tzinfo=timezone.utc),
    )
    quote = provider.quote("AAPL")
    assert quote.price == 103
    assert quote.change == 3
    assert quote.change_percent == 3
    assert quote.status == "latest available close"
    assert quote.delayed
    assert quote.source == "Yahoo Finance"
    assert quote.retrieved_at.startswith("2026-10-08T12:00:00")
    assert calls[0][0] == ("AAPL",)


def test_yahoo_adapter_caches_and_bounds_requests():
    count = []
    cache = BoundedMarketCache(max_entries=1)
    provider = YahooFinanceProvider(cache=cache, downloader=lambda *args, **kwargs: count.append(1) or frame(1, 2), clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    provider.quote("AAA")
    provider.quote("AAA")
    provider.quote("BBB")
    assert len(count) == 2


def test_yahoo_failure_is_nonfatal_and_cached_result_has_status():
    provider = YahooFinanceProvider(downloader=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network unavailable")))
    quote = provider.quote("AAPL")
    assert quote.price is None
    assert quote.status == "unavailable"
    assert "network unavailable" in quote.error
