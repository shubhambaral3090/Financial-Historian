"""Provider-isolated market data for the browser research page."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math
import re
import threading
from typing import Protocol

from .yahoo_access import (
    YahooRequestGate, safe_yahoo_error, yahoo_failure_kind, yahoo_request_gate, yahoo_session,
)


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
    as_of: str = ""
    currency: str = ""
    cached: bool = False
    stale: bool = False
    checked_at: str = ""


class MarketDataProvider(Protocol):
    def quote(self, ticker: str, period: str = "1y", *, force_refresh: bool = False) -> Quote: ...


class BoundedMarketCache:
    """Successful quotes only, with bounded size and bounded stale retention."""
    def __init__(self, max_entries: int = 128):
        self.max_entries = max(1, max_entries)
        self._items: OrderedDict[tuple[str, str], tuple[float, Quote]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[str, str], now: float, ttl: float) -> Quote | None:
        with self._lock:
            item = self._items.get(key)
            if not item or not 0 <= now - item[0] < ttl:
                return None
            self._items.move_to_end(key)
            return item[1]

    def put(self, key: tuple[str, str], now: float, value: Quote) -> None:
        if value.price is None or value.stale or value.error:
            return
        with self._lock:
            self._items[key] = (now, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)


def _utc_now(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _history_rows(frame, symbol: str) -> tuple[tuple[PricePoint, ...], str]:
    """Keep valid, sorted daily prices without guessing a different ticker column."""
    rows: dict[str, float] = {}
    index_tz = getattr(getattr(frame, "index", None), "tz", None)
    exchange_timezone = str(index_tz) if index_tz is not None else "unknown"
    for index, row in frame.iterrows():
        try:
            close = row["Close"]
            if hasattr(close, "index") and hasattr(close, "iloc"):
                if symbol not in close.index:
                    continue
                close = close.loc[symbol]
            value = float(close)
            if not math.isfinite(value) or value <= 0:
                continue
            day = index.date().isoformat() if hasattr(index.date(), "isoformat") else str(index.date())
            datetime.strptime(day, "%Y-%m-%d")
            rows[day] = value
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            continue
    return tuple(PricePoint(day, rows[day]) for day in sorted(rows)), exchange_timezone


class YahooFinanceProvider:
    """Yahoo adapter: delayed daily prices, never a guaranteed realtime feed.

    Page loads may force a new check. Widget reruns and sidebar suggestions use
    the successful five-minute cache. Failed refreshes retain last-good data for
    at most 24 hours, preserving its original retrieval and as-of timestamps.
    """
    def __init__(self, cache: BoundedMarketCache | None = None, ttl_seconds: float = 300,
                 downloader=None, clock=None, *, gate: YahooRequestGate | None = None,
                 max_stale_seconds: float = 86400, failure_ttl_seconds: float = 60):
        self.cache = cache or BoundedMarketCache()
        self.ttl_seconds = max(0.0, ttl_seconds)
        self.max_stale_seconds = max(self.ttl_seconds, max_stale_seconds)
        self.failure_ttl_seconds = max(0.0, failure_ttl_seconds)
        self.downloader = downloader
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.gate = gate or yahoo_request_gate()
        self._request_lock = threading.Lock()
        self._failures: OrderedDict[tuple[str, str], tuple[float, str]] = OrderedDict()

    def _download(self, symbol: str, period: str):
        if self.downloader is not None:
            result = self.downloader(symbol, period=period, interval="1d", auto_adjust=False,
                                     progress=False, threads=False, timeout=10)
            return result if isinstance(result, tuple) else (result, {})
        import yfinance as yf
        ticker = yf.Ticker(symbol, session=yahoo_session())
        frame = ticker.history(period=period, interval="1d", auto_adjust=False,
                               actions=False, raise_errors=True, timeout=10)
        # Public metadata can require one extra request. Metadata failure must
        # not discard usable prices or invent a currency for the instrument.
        try:
            metadata = ticker.get_history_metadata() or {}
        except Exception:
            metadata = {}
        return frame, metadata

    def _failed(self, symbol: str, key: tuple[str, str], now: datetime, kind: str) -> Quote:
        cached = self.cache.get(key, now.timestamp(), self.max_stale_seconds)
        message = safe_yahoo_error(kind)
        if cached is not None:
            return replace(cached, cached=True, stale=True, error=message, checked_at=now.isoformat())
        return Quote(symbol, None, None, None, (), "Yahoo Finance", "", "unknown", "unavailable",
                     error=message, checked_at=now.isoformat())

    def quote(self, ticker: str, period: str = "1y", *, force_refresh: bool = False) -> Quote:
        symbol = str(ticker or "").strip().upper().replace(".", "-")
        now = _utc_now(self.clock())
        key = (symbol, period)
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9^-]{0,19}", symbol) or period not in {"1mo", "3mo", "6mo", "1y", "2y", "5y"}:
            return self._failed(symbol, key, now, "malformed")
        # Serialize misses; concurrent requests can reuse a completed cache fill.
        with self._request_lock:
            now = _utc_now(self.clock())
            failure = self._failures.get(key)
            if failure and 0 <= now.timestamp() - failure[0] < self.failure_ttl_seconds:
                self._failures.move_to_end(key)
                return self._failed(symbol, key, now, failure[1])
            cached = self.cache.get(key, now.timestamp(), self.ttl_seconds)
            if cached is not None and not force_refresh and failure is None:
                return replace(cached, cached=True)
            try:
                frame, metadata = self.gate.run(lambda: self._download(symbol, period))
                rows, exchange_timezone = _history_rows(frame, symbol)
                if not rows:
                    raise ValueError("No usable daily prices")
                if not isinstance(metadata, dict):
                    metadata = {}
                exchange_timezone = str(metadata.get("exchangeTimezoneName") or exchange_timezone)
                currency = str(metadata.get("currency") or "")
                if not re.fullmatch(r"[A-Za-z]{3,6}", currency):
                    currency = ""
                price = rows[-1].close
                previous = rows[-2].close if len(rows) > 1 else None
                change = price - previous if previous is not None else None
                percent = change / previous * 100 if change is not None and previous else None
                completed = _utc_now(self.clock())
                # Today's daily bar can still move. A bar date is not an exact
                # quote timestamp, so its precision is preserved as a date.
                status = "latest available close" if rows[-1].timestamp < completed.date().isoformat() else "delayed daily price"
                result = Quote(symbol, price, change, percent, rows, "Yahoo Finance", completed.isoformat(),
                               exchange_timezone, status, as_of=rows[-1].timestamp, currency=currency,
                               checked_at=completed.isoformat())
            except Exception as exc:
                kind = yahoo_failure_kind(exc)
                failed_at = _utc_now(self.clock())
                self._failures[key] = (failed_at.timestamp(), kind)
                self._failures.move_to_end(key)
                while len(self._failures) > self.cache.max_entries:
                    self._failures.popitem(last=False)
                return self._failed(symbol, key, failed_at, kind)
            self._failures.pop(key, None)
            self.cache.put(key, completed.timestamp(), result)
            return result
