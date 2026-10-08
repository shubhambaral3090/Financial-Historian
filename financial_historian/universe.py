"""Configurable suggestion groups, separate from SEC identity.

The pinned yfinance release does not document an S&P 500 or Nasdaq-100
membership screener. The default screens therefore provide *general* market
suggestions and never imply index membership. Operators can configure a real,
verified index-specific Yahoo screen when one is available; invented IDs and
NASDAQ-exchange filters are not substitutes for index constituents.
"""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import random
import re
import threading
from typing import Callable
from urllib.parse import urlencode

from .models import Company


SOURCE = "Yahoo Finance market-universe data"
MANUAL_SOURCE = "Manually maintained ticker groups · Yahoo Finance prices"
MANUAL_STATUS = "Manually configured; not independently verified"
MANUAL_CONFIG = Path(__file__).resolve().parents[1] / "config" / "ticker_groups.json"
SCREENER_ENDPOINT = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
CONFIG_ENV = "FINANCIAL_HISTORIAN_YAHOO_SCREENERS"
INDEX_LIMITATION = (
    "These are general Yahoo Finance market suggestions, not verified S&P 500 "
    "or Nasdaq-100 membership. Direct company search remains available."
)
_ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,19}\Z")
_INDEX_NAMES = frozenset({"S&P 500", "Nasdaq-100"})


class UniverseConfigError(ValueError):
    """Configuration is invalid; messages intentionally exclude raw inputs."""


class InvalidScreenerResponse(ValueError):
    """A response cannot safely replace a last-successful suggestion list."""


@dataclass(frozen=True)
class ScreenerGroup:
    screener_id: str
    label: str
    indexes: tuple[str, ...] = ()
    membership_verified: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.screener_id, str) or not _ID.fullmatch(self.screener_id):
            raise UniverseConfigError("Yahoo screener identifiers must be simple saved-screen IDs.")
        if not isinstance(self.label, str) or not self.label.strip() or len(self.label) > 100:
            raise UniverseConfigError("Each Yahoo screen needs a short display label.")
        if not isinstance(self.indexes, tuple) or any(index not in _INDEX_NAMES for index in self.indexes):
            raise UniverseConfigError("Only S&P 500 and Nasdaq-100 index labels are supported.")
        if not isinstance(self.membership_verified, bool):
            raise UniverseConfigError("Index-membership verification must be explicit.")

    @property
    def source_url(self) -> str:
        return SCREENER_ENDPOINT + "?" + urlencode({"scrIds": self.screener_id})


DEFAULT_GROUPS = (
    ScreenerGroup("most_actives", "Most active U.S. stocks"),
    ScreenerGroup("day_gainers", "U.S. daily gainers"),
)


def load_screener_groups(config: str | None = None) -> tuple[ScreenerGroup, ...]:
    """Read optional JSON group configuration; never interpret URLs as screens.

    Example: ``[{"id":"most_actives","label":"Most active stocks"}]``.
    ``indexes`` requires an explicit ``membership_verified: true`` assertion by
    the operator. General screens must not be relabeled as index constituents.
    """
    raw = os.environ.get(CONFIG_ENV, "") if config is None else config
    if not raw:
        return DEFAULT_GROUPS
    try:
        records = json.loads(raw)
        if not isinstance(records, list) or not 1 <= len(records) <= 8:
            raise UniverseConfigError("Configure between one and eight Yahoo screens.")
        result = []
        for record in records:
            if not isinstance(record, dict) or set(record) - {"id", "label", "indexes", "membership_verified"}:
                raise UniverseConfigError("The Yahoo screen configuration contains unsupported fields.")
            indexes = record.get("indexes", [])
            if not isinstance(indexes, list):
                raise UniverseConfigError("Configured index labels must be a list.")
            result.append(ScreenerGroup(
                record["id"], record.get("label", record["id"]), tuple(indexes),
                record.get("membership_verified", False),
            ))
        if len({group.screener_id for group in result}) != len(result):
            raise UniverseConfigError("Configure each Yahoo screen only once.")
        return tuple(result)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise UniverseConfigError("The Yahoo screen configuration is not valid JSON group data.") from exc


@dataclass(frozen=True)
class UniverseMember:
    company: Company
    indexes: tuple[str, ...]
    source_url: str
    retrieved_at: str
    groups: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    membership_status: str = "Not verified"


@dataclass(frozen=True)
class UniverseSnapshot:
    members: tuple[UniverseMember, ...] = ()
    retrieved_at: str = ""
    checked_at: str = ""
    warnings: tuple[str, ...] = ()
    stale: bool = False
    source: str = SOURCE
    group_timestamps: tuple[tuple[str, str], ...] = ()
    origin: str = "yahoo_screeners"
    maintained_at: str = ""
    membership_status: str = "Not verified"


def _screener_result(payload: object) -> dict:
    if isinstance(payload, dict) and "finance" in payload:
        envelope = payload.get("finance")
        if not isinstance(envelope, dict) or envelope.get("error"):
            raise InvalidScreenerResponse("Yahoo returned an unsuccessful screen response.")
        results = envelope.get("result")
        if not isinstance(results, list) or len(results) != 1:
            raise InvalidScreenerResponse("Yahoo returned an invalid screen envelope.")
        payload = results[0]
    if not isinstance(payload, dict):
        raise InvalidScreenerResponse("Yahoo returned an invalid screen response.")
    return payload


def parse_predefined_screener(
    payload: object, *, group: ScreenerGroup, retrieved_at: str, max_members: int = 250,
) -> tuple[UniverseMember, ...]:
    """Parse a yfinance ``screen`` result (or the original Yahoo envelope).

    Yahoo identities are suggestions only: a CIK in an upstream response is
    deliberately ignored. SEC resolution must independently validate it.
    """
    payload = _screener_result(payload)
    canonical = payload.get("canonicalName")
    if canonical is not None and (not isinstance(canonical, str) or canonical.casefold() != group.screener_id.casefold()):
        raise InvalidScreenerResponse("Yahoo returned a different screen than requested.")
    quotes = payload.get("quotes")
    if not isinstance(quotes, list) or not quotes or len(quotes) > max_members:
        raise InvalidScreenerResponse("Yahoo returned an empty or oversized screen response.")
    members: dict[str, UniverseMember] = {}
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        symbol = quote.get("symbol")
        if not isinstance(symbol, str):
            continue
        symbol = symbol.strip().upper()
        if not _SYMBOL.fullmatch(symbol) or quote.get("quoteType", "EQUITY") != "EQUITY":
            continue
        name = quote.get("longName") or quote.get("shortName")
        if not isinstance(name, str) or not name.strip():
            continue
        name = " ".join(name.split())[:200]
        indexes = tuple(sorted(set(group.indexes))) if group.membership_verified else ()
        members[symbol] = UniverseMember(
            Company("", name, symbol), indexes, group.source_url, retrieved_at,
            (group.label,), (group.source_url,),
            "Operator-verified screener membership" if indexes else "Not verified",
        )
    if not members:
        raise InvalidScreenerResponse("Yahoo returned no usable stock suggestions.")
    return tuple(sorted(members.values(), key=lambda member: member.company.ticker))


def shuffled_suggestions(
    snapshot: UniverseSnapshot, limit: int = 8, rng: random.Random | None = None,
) -> tuple[UniverseMember, ...]:
    """Shuffle an existing snapshot locally; this function never uses a provider."""
    members = list(snapshot.members)
    (rng or random.SystemRandom()).shuffle(members)
    return tuple(members[:max(0, int(limit))])


@dataclass(frozen=True)
class _CacheEntry:
    members: tuple[UniverseMember, ...]
    retrieved_at: str
    timestamp: float
    coverage_warning: str = ""


class YahooUniverseProvider:
    """Twelve-hour screen cache with bounded, explicitly stale failure fallback.

    At most eight screens × 250 members are held in memory. Failed or malformed
    responses never overwrite a successful entry. Last-good entries expire
    after seven days; failures have a five-minute retry cooldown. Calling
    ``load`` or shuffling repeatedly within the TTL does not request Yahoo.
    The injected ``fetch_screen`` callable accepts ``(id, count=250)``.
    """
    def __init__(
        self, fetch_screen: Callable | None = None, *, groups: tuple[ScreenerGroup, ...] | None = None,
        ttl_seconds: float = 12 * 60 * 60, stale_seconds: float = 7 * 24 * 60 * 60,
        retry_seconds: float = 300, clock: Callable[[], datetime] | None = None,
    ):
        if not 6 * 60 * 60 <= ttl_seconds <= 24 * 60 * 60:
            raise ValueError("The Yahoo universe TTL must be between six and 24 hours.")
        if not ttl_seconds <= stale_seconds <= 7 * 24 * 60 * 60:
            raise ValueError("Last-good Yahoo universe retention must be bounded to seven days.")
        self.groups = load_screener_groups() if groups is None else tuple(groups)
        if not 1 <= len(self.groups) <= 8 or len({g.screener_id for g in self.groups}) != len(self.groups):
            raise UniverseConfigError("Configure one to eight distinct Yahoo screens.")
        self.fetch_screen = fetch_screen or self._fetch_screen
        self.ttl_seconds = ttl_seconds
        self.stale_seconds = stale_seconds
        self.retry_seconds = max(1, min(float(retry_seconds), 3600))
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._entries: dict[str, _CacheEntry] = {}
        self._failures: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _fetch_screen(screener_id: str, *, count: int) -> dict:
        import yfinance as yf
        from .yahoo_access import yahoo_request_gate, yahoo_session
        return yahoo_request_gate().run(lambda: yf.screen(screener_id, count=count, session=yahoo_session()))

    @staticmethod
    def _failure_message(error: Exception) -> str:
        if isinstance(error, InvalidScreenerResponse):
            return "Yahoo returned an incomplete or unrecognized suggestion response."
        from .yahoo_access import safe_yahoo_error, yahoo_failure_kind
        return safe_yahoo_error(yahoo_failure_kind(error))

    def load(self) -> UniverseSnapshot:
        # Coalesce simultaneous browser sessions at the list-cache boundary.
        with self._lock:
            now_dt = self.clock().astimezone(timezone.utc)
            now, checked = now_dt.timestamp(), now_dt.isoformat()
            warnings: list[str] = []
            if any(not group.membership_verified or not group.indexes for group in self.groups):
                warnings.append(INDEX_LIMITATION)
            collected: list[UniverseMember] = []
            group_timestamps: list[tuple[str, str]] = []
            stale = False
            for group in self.groups:
                key = group.screener_id
                entry = self._entries.get(key)
                if entry is not None and now - entry.timestamp >= self.stale_seconds:
                    del self._entries[key]
                    entry = None
                fresh = entry is not None and 0 <= now - entry.timestamp < self.ttl_seconds
                failure = self._failures.get(key)
                cooling_down = failure is not None and now < failure[0]
                if not fresh and not cooling_down:
                    try:
                        payload = _screener_result(self.fetch_screen(key, count=250))
                        retrieved_dt = self.clock().astimezone(timezone.utc)
                        retrieved = retrieved_dt.isoformat()
                        members = parse_predefined_screener(payload, group=group, retrieved_at=retrieved)
                        total = payload.get("total")
                        coverage_warning = ""
                        if isinstance(total, int) and not isinstance(total, bool) and total > len(members):
                            coverage_warning = (
                                f"{group.label}: showing {len(members)} returned stock suggestions "
                                f"out of {total} screen matches; this is not a complete membership list."
                            )
                        elif group.membership_verified and group.indexes and total is None:
                            coverage_warning = (
                                f"{group.label}: membership reflects returned records only; "
                                "the provider did not confirm a complete constituent count."
                            )
                        entry = _CacheEntry(members, retrieved, retrieved_dt.timestamp(), coverage_warning)
                        self._entries[key] = entry
                        self._failures.pop(key, None)
                        failure = None
                    except Exception as error:
                        failure = (now + self.retry_seconds, self._failure_message(error))
                        self._failures[key] = failure
                if failure is not None and not fresh:
                    if entry is not None:
                        stale = True
                        warnings.append(
                            f"{group.label}: {failure[1]} Showing the last successful list "
                            f"retrieved {entry.retrieved_at}; it may be outdated."
                        )
                    else:
                        warnings.append(f"{group.label}: {failure[1]} Direct SEC company search remains available.")
                if entry is not None:
                    collected.extend(entry.members)
                    group_timestamps.append((group.label, entry.retrieved_at))
                    if entry.coverage_warning:
                        warnings.append(entry.coverage_warning)

            merged: dict[str, UniverseMember] = {}
            for member in collected:
                symbol = member.company.ticker
                prior = merged.get(symbol)
                if prior is None:
                    merged[symbol] = member
                else:
                    merged[symbol] = UniverseMember(
                        prior.company, tuple(sorted(set(prior.indexes + member.indexes))),
                        prior.source_url, min(prior.retrieved_at, member.retrieved_at),
                        tuple(sorted(set(prior.groups + member.groups))),
                        tuple(sorted(set(prior.source_urls + member.source_urls))),
                        prior.membership_status,
                    )
            members = tuple(sorted(merged.values(), key=lambda member: (member.company.name.casefold(), member.company.ticker)))
            retrieved = min((stamp for _, stamp in group_timestamps), default="")
            return UniverseSnapshot(members, retrieved, checked, tuple(warnings), stale, SOURCE, tuple(group_timestamps))

    def companies(self) -> list[Company]:
        return [member.company for member in self.load().members]


def parse_ticker_groups(payload: object, *, checked_at: str) -> UniverseSnapshot:
    """Parse user-maintained groups without representing them as Yahoo membership.

    ``maintained_at`` dates file maintenance only. It is deliberately separate
    from provider retrieval time and is not an independently verified index date.
    """
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise UniverseConfigError("The ticker-group file needs schema_version 1.")
    maintained = payload.get("maintained_at")
    try:
        if not isinstance(maintained, str) or date.fromisoformat(maintained).isoformat() != maintained:
            raise ValueError()
    except ValueError as exc:
        raise UniverseConfigError("The ticker-group file needs a YYYY-MM-DD maintenance date.") from exc
    groups = payload.get("groups")
    if not isinstance(groups, list) or not 1 <= len(groups) <= 2:
        raise UniverseConfigError("Configure the S&P 500 and/or Nasdaq-100 ticker groups.")
    seen_groups: set[str] = set()
    members: dict[str, UniverseMember] = {}
    warnings = [
        "Index labels are manually configured, not independently verified current membership. "
        "The maintenance date describes this file, not a Yahoo universe retrieval or official index review."
    ]
    for group in groups:
        if not isinstance(group, dict) or group.get("name") not in _INDEX_NAMES:
            raise UniverseConfigError("Ticker-group names must be S&P 500 or Nasdaq-100.")
        name = group["name"]
        if name in seen_groups:
            raise UniverseConfigError("Configure each index group only once.")
        seen_groups.add(name)
        tickers = group.get("tickers")
        if not isinstance(tickers, list) or not 1 <= len(tickers) <= 1000:
            raise UniverseConfigError("Each ticker group needs one to 1,000 named stock tickers.")
        complete = group.get("complete", False)
        if not isinstance(complete, bool):
            raise UniverseConfigError("Ticker-group completeness must be true or false.")
        if not complete:
            warnings.append(f"{name}: incomplete starter group, not the full index. Edit config/ticker_groups.json to maintain the list.")
        for record in tickers:
            if not isinstance(record, dict):
                raise UniverseConfigError("Each configured ticker needs a symbol and company name.")
            symbol, company_name = record.get("symbol"), record.get("name")
            if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol.strip().upper()):
                raise UniverseConfigError("The ticker-group file contains an invalid stock symbol.")
            if not isinstance(company_name, str) or not company_name.strip() or len(company_name) > 200:
                raise UniverseConfigError("Each configured ticker needs a short company name.")
            symbol = symbol.strip().upper()
            prior = members.get(symbol)
            indexes = tuple(sorted(set((prior.indexes if prior else ()) + (name,))))
            members[symbol] = UniverseMember(
                Company("", " ".join(company_name.split()), symbol), indexes,
                "", "", indexes, (), MANUAL_STATUS,
            )
    return UniverseSnapshot(
        members=tuple(sorted(members.values(), key=lambda member: (member.company.name.casefold(), member.company.ticker))),
        checked_at=checked_at, warnings=tuple(warnings), source=MANUAL_SOURCE,
        origin="manual_ticker_groups", maintained_at=maintained, membership_status=MANUAL_STATUS,
    )


class ManualUniverseProvider:
    """Read a bounded local ticker configuration; make no Yahoo or SEC requests."""
    def __init__(self, config_path: Path | str | None = None, *, clock=None):
        self.config_path = Path(config_path) if config_path is not None else MANUAL_CONFIG
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_good: UniverseSnapshot | None = None
        self._fingerprint: tuple[int, int] | None = None
        self._loaded_at: float = 0
        self._lock = threading.Lock()

    def load(self) -> UniverseSnapshot:
        with self._lock:
            now = self.clock().astimezone(timezone.utc)
            try:
                stat = self.config_path.stat()
                if stat.st_size > 1_000_000:
                    raise UniverseConfigError("The ticker-group configuration exceeds the one-megabyte limit.")
                fingerprint = (stat.st_mtime_ns, stat.st_size)
                if self._last_good is not None and fingerprint == self._fingerprint and now.timestamp() - self._loaded_at < 12 * 3600:
                    return replace(self._last_good, checked_at=now.isoformat())
                payload = json.loads(self.config_path.read_text(encoding="utf-8"))
                result = parse_ticker_groups(payload, checked_at=now.isoformat())
                self._last_good, self._fingerprint, self._loaded_at = result, fingerprint, now.timestamp()
                return result
            except (OSError, UnicodeError, json.JSONDecodeError, UniverseConfigError):
                warning = "The manually maintained ticker file could not be loaded. Direct SEC company search remains available."
                if self._last_good is not None and now.timestamp() - self._loaded_at < 7 * 24 * 3600:
                    return replace(
                        self._last_good, checked_at=now.isoformat(), stale=True,
                        warnings=self._last_good.warnings + (warning + " Showing the last successfully read local list.",),
                    )
                self._last_good = None
                return UniverseSnapshot(
                    checked_at=now.isoformat(), warnings=(warning,), source=MANUAL_SOURCE,
                    origin="manual_ticker_groups", membership_status=MANUAL_STATUS,
                )

    def companies(self) -> list[Company]:
        return [member.company for member in self.load().members]


class UniverseProvider:
    """Use approved manual groups by default; Yahoo screens are an opt-in.

    Set ``FINANCIAL_HISTORIAN_YAHOO_SCREENERS`` to JSON saved-screen groups to
    choose the optional Yahoo path. Injecting ``groups`` or ``fetch_screen``
    also selects that path, primarily for isolated provider tests.
    """
    def __init__(self, fetch_screen=None, *, groups=None, config_path=None, clock=None, **kwargs):
        if fetch_screen is not None or groups is not None or os.environ.get(CONFIG_ENV):
            self._provider = YahooUniverseProvider(fetch_screen, groups=groups, clock=clock, **kwargs)
        else:
            self._provider = ManualUniverseProvider(config_path=config_path, clock=clock)

    def load(self) -> UniverseSnapshot:
        return self._provider.load()

    def companies(self) -> list[Company]:
        return self._provider.companies()
