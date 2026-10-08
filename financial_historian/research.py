"""Automatic, provider-independent research-page orchestration.

Workers never call browser/UI functions. Progress and partial results are
delivered on the caller thread so one unavailable provider cannot hide the
other. The bounded cache contains public results only, never SEC clients or
contact information, and never survives the application process.
"""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import pickle
from queue import Empty, Queue
from threading import Lock
from time import perf_counter
from typing import Callable

from .export import build_workbook
from .analysis import Analysis, build_analysis
from .market import MarketDataProvider, Quote
from .models import Company, StatementBundle
from .presentation import prepare_presentation
from .service import FinancialHistorian, limit_statement_history, normalize_ticker


@dataclass(frozen=True)
class ResearchEvent:
    kind: str
    message: str = ""
    company: Company | None = None
    quote: Quote | None = None
    bundle: StatementBundle | None = None
    workbook: bytes | None = None
    sec_retrieved_at: str = ""
    workbook_generated_at: str = ""
    duration_seconds: float | None = None
    analysis: Analysis | None = None


@dataclass(frozen=True)
class ResearchResult:
    company: Company
    quote: Quote | None = None
    bundle: StatementBundle | None = None
    workbook: bytes | None = None
    sec_retrieved_at: str = ""
    workbook_generated_at: str = ""
    warnings: tuple[str, ...] = ()
    market_error: str = ""
    sec_error: str = ""
    workbook_error: str = ""
    sec_stale: bool = False
    analysis: Analysis | None = None


@dataclass(frozen=True)
class _FinancialSnapshot:
    company: Company
    bundle: bytes
    workbook: bytes
    retrieved_at: str
    workbook_generated_at: str
    stored_at: float
    generation: int

    @property
    def size(self) -> int:
        return len(self.bundle) + len(self.workbook)


class ResearchController:
    """Load automatically; retain at most eight successful financial snapshots.

    The 64 MiB cap applies to the serialized bundle and workbook payloads.
    Entries expire after 24 hours, including stale-on-error fallbacks. A full
    browser refresh must pass ``force_refresh=True``. The UI should retain its
    ResearchResult through ordinary widget reruns instead of loading again.
    """

    def __init__(self, *, max_entries: int = 8, max_bytes: int = 64 * 1024 * 1024,
                 retention_seconds: float = 24 * 3600, freshness_seconds: float = 300, clock=None, exporter=None):
        self.max_entries = max(1, max_entries)
        self.max_bytes = max(1, max_bytes)
        self.retention_seconds = max(0, retention_seconds)
        self.freshness_seconds = max(0, freshness_seconds)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.exporter = exporter or build_workbook
        self._snapshots: OrderedDict[str, _FinancialSnapshot] = OrderedDict()
        self._lock = Lock()
        self._generation = 0

    def _cached(self, company: Company) -> _FinancialSnapshot | None:
        now = self.clock().timestamp()
        with self._lock:
            for key in list(self._snapshots):
                if now - self._snapshots[key].stored_at >= self.retention_seconds:
                    del self._snapshots[key]
            for key, item in list(self._snapshots.items()):
                same_ticker = (not company.ticker
                               or normalize_ticker(company.ticker) == normalize_ticker(item.company.ticker))
                if ((company.cik and company.cik.zfill(10) == item.company.cik and same_ticker)
                        or (not company.cik and company.ticker
                            and normalize_ticker(company.ticker) == normalize_ticker(item.company.ticker))):
                    self._snapshots.move_to_end(key)
                    return item
        return None

    def _store(self, result: ResearchResult, generation: int) -> None:
        if result.bundle is None or result.workbook is None:
            return
        # These bytes are generated here, never accepted from a user or disk.
        snapshot = _FinancialSnapshot(result.company, pickle.dumps((result.bundle, result.analysis)), result.workbook,
                                      result.sec_retrieved_at, result.workbook_generated_at,
                                      self.clock().timestamp(), generation)
        if snapshot.size > self.max_bytes:
            return
        with self._lock:
            current = self._snapshots.get(result.company.cik)
            if current is not None and current.generation > generation:
                return
            self._snapshots[result.company.cik] = snapshot
            self._snapshots.move_to_end(result.company.cik)
            while (len(self._snapshots) > self.max_entries
                   or sum(item.size for item in self._snapshots.values()) > self.max_bytes):
                self._snapshots.popitem(last=False)

    @staticmethod
    def _from_snapshot(snapshot: _FinancialSnapshot, *, stale: bool = False) -> ResearchResult:
        bundle, analysis = pickle.loads(snapshot.bundle)
        return ResearchResult(snapshot.company, bundle=bundle, workbook=snapshot.workbook,
                              sec_retrieved_at=snapshot.retrieved_at,
                              workbook_generated_at=snapshot.workbook_generated_at,
                              warnings=tuple(bundle.warnings), sec_stale=stale, analysis=analysis)

    def load(self, service: FinancialHistorian, company: Company, market: MarketDataProvider,
             *, force_refresh: bool = True,
             on_event: Callable[[ResearchEvent], None] | None = None) -> ResearchResult:
        """Return matching display/export data, emitting partial results promptly.

        SEC validation and market requests run independently. A CIK-only search
        starts its quote once the SEC profile supplies a ticker. Errors are
        deliberately generic: upstream exception messages can contain private
        request headers and must never reach logs, browser messages or exports.
        """
        events: Queue[ResearchEvent] = Queue()
        deliver = on_event or (lambda event: None)
        result = ResearchResult(company)
        with self._lock:
            self._generation += 1
            generation = self._generation
        previous = self._cached(company)

        def progress(message: str) -> None:
            events.put(ResearchEvent("progress", message))

        def timing(stage, started):
            events.put(ResearchEvent("timing", stage, duration_seconds=perf_counter()-started))

        def failure(stage, error):
            # Only a built-in exception class name, never its message/headers.
            name = type(error).__name__ if type(error).__module__ == "builtins" else "ProviderError"
            events.put(ResearchEvent("diagnostic", stage + ":" + name))

        def financial_work() -> ResearchResult:
            if (not force_refresh and previous is not None
                    and self.clock().timestamp()-previous.stored_at < self.freshness_seconds):
                cached = self._from_snapshot(previous)
                events.put(ResearchEvent("company", company=cached.company))
                events.put(ResearchEvent("financial", "Using cached SEC financial statements",
                                         bundle=cached.bundle, sec_retrieved_at=cached.sec_retrieved_at))
                events.put(ResearchEvent("workbook", workbook=cached.workbook,
                                         workbook_generated_at=cached.workbook_generated_at, analysis=cached.analysis))
                return cached
            resolved = company
            fallback = previous
            try:
                progress("Loading company profile")
                started = perf_counter()
                resolved = service.resolve_company(company)
                timing("company_profile", started)
                # Tickers can be reassigned. A newly verified issuer must not
                # inherit an old issuer's cached financial statements.
                if fallback is not None and resolved.cik != fallback.company.cik:
                    fallback = None
                events.put(ResearchEvent("company", company=resolved))
                progress("Retrieving SEC filings")
                started = perf_counter()
                bundle = prepare_presentation(limit_statement_history(service.generate(resolved, progress=progress), 20))
                timing("sec_retrieval_and_parsing", started)
                has_values = any(row.values for rows in bundle.statements.values() for row in rows)
                provider_failed = any(warning.startswith((
                    "Structured company-facts data could not be loaded:",
                    "One or more SEC filing documents could not be retrieved;")) for warning in bundle.warnings)
                if fallback is not None and not has_values and provider_failed:
                    old = self._from_snapshot(fallback)
                    if any(row.values for rows in old.bundle.statements.values() for row in rows):
                        raise RuntimeError("Failed refresh contains no financial observations")
                retrieved_at = self.clock().isoformat()
                bundle = replace(bundle, generated_at=retrieved_at)
            except Exception as error:
                failure("sec", error)
                message = ("SEC financial information could not be refreshed. "
                           "Market information remains available; refresh the browser to check again.")
                if fallback is not None:
                    stale = self._from_snapshot(fallback, stale=True)
                    warning = ("SEC refresh failed. Displaying the last successful cached statements and matching "
                               "workbook from " + stale.sec_retrieved_at + "; these are not newly retrieved data.")
                    events.put(ResearchEvent("financial", warning, bundle=stale.bundle,
                                             sec_retrieved_at=stale.sec_retrieved_at))
                    events.put(ResearchEvent("workbook", workbook=stale.workbook,
                                             workbook_generated_at=stale.workbook_generated_at, analysis=stale.analysis))
                    return replace(stale, sec_error=message, warnings=stale.warnings + (warning,))
                return ResearchResult(resolved, sec_error=message)
            events.put(ResearchEvent("financial", "Preparing financial statements", bundle=bundle,
                                     sec_retrieved_at=retrieved_at))
            partial = ResearchResult(resolved, bundle=bundle, sec_retrieved_at=retrieved_at,
                                     warnings=tuple(bundle.warnings))
            try:
                started = perf_counter()
                analysis = build_analysis(bundle)
                partial = replace(partial, analysis=analysis)
                timing("analysis", started)
                progress("Building Excel workbook")
                started = perf_counter()
                workbook = (self.exporter(bundle, progress=progress, analysis=analysis)
                            if self.exporter is build_workbook else self.exporter(bundle, progress=progress))
                if not isinstance(workbook, bytes) or not workbook:
                    raise ValueError("Empty export")
                generated_at = self.clock().isoformat()
                timing("excel", started)
            except Exception as error:
                failure("workbook", error)
                # Never attach an older workbook to newly retrieved statements.
                return replace(partial, workbook_error="The Excel workbook could not be built. "
                               "The financial statements remain available; refresh the browser to check again.")
            completed = replace(partial, workbook=workbook, workbook_generated_at=generated_at)
            # A partial network response can still be useful on this page, but
            # must not displace a complete last-good snapshot. Unsupported
            # filing formats/coverage limitations alone are not network errors.
            if not provider_failed:
                self._store(completed, generation)
            events.put(ResearchEvent("workbook", workbook=workbook, workbook_generated_at=generated_at, analysis=analysis))
            return completed

        def market_work(ticker: str) -> tuple[Quote | None, str]:
            progress("Loading market data")
            started = perf_counter()
            try:
                quote = market.quote(normalize_ticker(ticker), force_refresh=force_refresh)
                error = ("Yahoo Finance market data is unavailable. SEC financial information is independent; "
                         "refresh the browser to check again.") if quote.price is None else ""
                events.put(ResearchEvent("market", quote=quote, message=error))
                return quote, error
            except Exception as error:
                failure("market", error)
                error = ("Yahoo Finance market data is unavailable. SEC financial information is independent; "
                         "refresh the browser to check again.")
                events.put(ResearchEvent("market", message=error))
                return None, error
            finally:
                timing("market", started)

        # No contact/client references are retained after this call completes.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="financial-research") as executor:
            market_future = executor.submit(market_work, company.ticker) if company.ticker else None
            financial_future = executor.submit(financial_work)
            while True:
                try:
                    event = events.get(timeout=0.05)
                    deliver(event)
                    if event.kind == "company" and market_future is None and event.company.ticker:
                        market_future = executor.submit(market_work, event.company.ticker)
                except Empty:
                    if financial_future.done() and (market_future is None or market_future.done()):
                        break
            result = financial_future.result()
            if market_future is not None:
                quote, error = market_future.result()
                result = replace(result, quote=quote, market_error=error)
        return result
