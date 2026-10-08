"""Supported-company universe discovery.

The public index pages are treated as a discoverable directory, not as an
authority for financial facts. Every record carries the page and retrieval time
so membership changes remain auditable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Callable

from .models import Company

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"


@dataclass(frozen=True)
class UniverseMember:
    company: Company
    indexes: tuple[str, ...]
    source_url: str
    retrieved_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_ticker(value: object) -> str:
    # Yahoo uses '-' where SEC/index tables commonly use '.'.
    return str(value or "").strip().upper().replace(".", "-")


def _clean_cik(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(10) if digits else ""


def _records_from_table(rows, source: str, index: str, retrieved: str) -> list[UniverseMember]:
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = _clean_ticker(row.get("Symbol") or row.get("Ticker") or row.get("Ticker symbol"))
        name = str(row.get("Security") or row.get("Company") or row.get("Name") or "").strip()
        cik = _clean_cik(row.get("CIK") or row.get("CIK number"))
        if ticker and name:
            result.append(UniverseMember(Company(cik, name, ticker), (index,), source, retrieved))
    return result


def parse_wikipedia_tables(tables: list, *, source_url: str, index: str,
                           retrieved_at: str | None = None) -> list[UniverseMember]:
    """Parse pandas-like records while keeping the provider easy to mock."""
    return _records_from_table(tables, source_url, index, retrieved_at or _now())


class UniverseProvider:
    """Fetch and merge the two supported index directories.

    ``fetch_tables`` is injectable for tests. The default intentionally imports
    pandas only at call time because the SEC application does not need it for a
    filing-only workflow.
    """
    def __init__(self, fetch_tables: Callable[[str], list] | None = None):
        self.fetch_tables = fetch_tables or self._fetch_tables

    @staticmethod
    def _fetch_tables(url: str) -> list:
        import pandas as pd
        return pd.read_html(url)[0].to_dict("records") if url == SP500_URL else pd.read_html(url)[4].to_dict("records")

    def load(self) -> list[UniverseMember]:
        retrieved = _now()
        members: dict[tuple[str, str], UniverseMember] = {}
        sources = ((SP500_URL, "S&P 500"), (NASDAQ100_URL, "Nasdaq-100"))
        for url, index in sources:
            for member in parse_wikipedia_tables(self.fetch_tables(url), source_url=url, index=index, retrieved_at=retrieved):
                key = (member.company.ticker, member.company.cik or member.company.name.casefold())
                prior = members.get(key)
                if prior:
                    members[key] = UniverseMember(prior.company, tuple(sorted(set(prior.indexes + member.indexes))), prior.source_url, prior.retrieved_at)
                else:
                    members[key] = member
        return sorted(members.values(), key=lambda item: (item.company.name.casefold(), item.company.ticker))

    def companies(self) -> list[Company]:
        return [member.company for member in self.load()]
