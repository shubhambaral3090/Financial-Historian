"""Shared, bounded Yahoo access without credentials or a persistent data archive."""
from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from typing import TypeVar


_T = TypeVar("_T")


class YahooAccessCooldown(RuntimeError):
    def __init__(self, kind: str, retry_after: float):
        super().__init__(safe_yahoo_error(kind))
        self.kind = kind
        self.retry_after = max(0.0, retry_after)


def yahoo_failure_kind(exc: Exception) -> str:
    """Classify privately: exception text and URLs are never presented to users."""
    if isinstance(exc, YahooAccessCooldown):
        return exc.kind
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
    description = str(exc).lower()
    name = type(exc).__name__.lower()
    if status == 429 or "ratelimit" in name or re.search(r"\b429\b", description):
        return "rate_limit"
    if status == 403 or re.search(r"\b403\b", description):
        return "forbidden"
    if "timeout" in name or "timed out" in description or "timeout" in description:
        return "timeout"
    if isinstance(exc, (ValueError, KeyError, TypeError, AttributeError)):
        return "malformed"
    return "unavailable"


def safe_yahoo_error(kind: str) -> str:
    return {
        "rate_limit": "Yahoo Finance is temporarily limiting requests. Refresh the browser later to check again.",
        "forbidden": "Yahoo Finance declined this request. SEC financial retrieval remains available.",
        "timeout": "Yahoo Finance did not respond in time. SEC financial retrieval remains available.",
        "malformed": "Yahoo Finance did not return usable market data. SEC financial retrieval remains available.",
    }.get(kind, "Yahoo Finance market data is temporarily unavailable. SEC financial retrieval remains available.")


class YahooRequestGate:
    """Serialize Yahoo operations, pace calls, and fail fast during a cooldown.

    The gate is shared by quotes and screeners. Cooldowns never sleep a page for
    their full duration, and a provider failure does not hold up SEC work.
    """

    def __init__(self, min_interval_seconds: float = 0.5, *, clock=None, sleep=None):
        self.min_interval_seconds = max(0.0, min(2.0, min_interval_seconds))
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._last_started: float | None = None
        self._cooldown_until = 0.0
        self._failure_kind = "unavailable"

    def run(self, operation: Callable[[], _T]) -> _T:
        with self._lock:
            now = self.clock()
            if now < self._cooldown_until:
                raise YahooAccessCooldown(self._failure_kind, self._cooldown_until - now)
            if self._last_started is not None:
                wait = self.min_interval_seconds - (now - self._last_started)
                if wait > 0:
                    self.sleep(wait)
            self._last_started = self.clock()
            try:
                return operation()
            except Exception as exc:
                kind = yahoo_failure_kind(exc)
                self._failure_kind = kind
                seconds = 60.0 if kind in {"forbidden", "rate_limit"} else 5.0
                self._cooldown_until = self.clock() + seconds
                raise


_GATE = YahooRequestGate()
_SESSION = None
_SESSION_LOCK = threading.Lock()


def yahoo_request_gate() -> YahooRequestGate:
    return _GATE


def yahoo_session():
    """Use yfinance's supported session interface with bounded request timeouts."""
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is None:
            from curl_cffi.requests import Session

            class BoundedYahooSession(Session):
                def request(self, method, url, **kwargs):
                    timeout = kwargs.get("timeout", 10.0)
                    if isinstance(timeout, (int, float)) and timeout > 0:
                        kwargs["timeout"] = min(float(timeout), 10.0)
                    else:
                        kwargs["timeout"] = 10.0
                    return super().request(method, url, **kwargs)

            _SESSION = BoundedYahooSession(impersonate="chrome")
        return _SESSION
