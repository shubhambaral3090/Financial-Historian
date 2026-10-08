"""Provider-isolated market data for the browser research page."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
from typing import Protocol


@dataclass(frozen=True)
class PricePoint:
    timestamp: str
    close: float


@dataclass(frozen=True)
class Quote:
    ticker: str
    price: float | None
    change: float | None
    change_percent: float | None
    history: tuple[PricePoint, ...]
    source: str
    retrieved_at: str
    timezone: str
    status: str
    delayed: bool = True
    error: str = ""


class MarketDataProvider(Protocol):
    def quote(self, ticker: str, period: str = "1y") -> Quote: ...


class BoundedMarketCache:
    """Small in-memory cache; it is deliberately not a permanent archive."""
    def __init__(self, max_entries: int = 128):
        self.max_entries = max(1, max_entries)
        self._items: OrderedDict[tuple[str, str], tuple[float, Quote]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[str, str], now: float, ttl: float) -> Quote | None:
        with self._lock:
            item = self._items.get(key)
            if not item or now - item[0] >= ttl:
                return None
            self._items.move_to_end(key)
            return item[1]

    def put(self, key: tuple[str, str], now: float, value: Quote) -> None:
        with self._lock:
            self._items[key] = (now, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)


class YahooFinanceProvider:
    """Yahoo adapter. Quotes are explicitly latest-close/delayed, never realtime."""
    def __init__(self, cache: BoundedMarketCache | None = None, ttl_seconds: float = 300,
                 downloader=None, clock=None):
        self.cache = cache or BoundedMarketCache()
        self.ttl_seconds = ttl_seconds
        self.downloader = downloader
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def quote(self, ticker: str, period: str = "1y") -> Quote:
        symbol = str(ticker or "").strip().upper()
        now_dt = self.clock()
        now = now_dt.timestamp()
        key = (symbol, period)
        cached = self.cache.get(key, now, self.ttl_seconds)
        if cached:
            return cached
        retrieved = now_dt.isoformat()
        try:
            download = self.downloader
            if download is None:
                import yfinance as yf
                download = yf.download
            frame = download(symbol, period=period, interval="1d", auto_adjust=False, progress=False, threads=False)
            rows = []
            for index, row in frame.iterrows():
                try:
                    value = float(row["Close"].iloc[0] if hasattr(row["Close"], "iloc") else row["Close"])
                    if value == value:
                        rows.append(PricePoint(str(index.date()), value))
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue
            price = rows[-1].close if rows else None
            previous = rows[-2].close if len(rows) > 1 else None
            change = price - previous if price is not None and previous is not None else None
            percent = (change / previous * 100) if change is not None and previous else None
            status = "latest available close" if price is not None else "unavailable"
            result = Quote(symbol, price, change, percent, tuple(rows), "Yahoo Finance", retrieved, "UTC", status, True)
        except Exception as exc:
            result = Quote(symbol, None, None, None, (), "Yahoo Finance", retrieved, "UTC", "unavailable", True, str(exc))
        self.cache.put(key, now, result)
        return result
