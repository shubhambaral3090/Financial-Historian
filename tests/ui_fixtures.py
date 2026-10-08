"""Fictional, entirely in-memory providers for offline UI and browser tests."""
from datetime import datetime, timezone
from financial_historian.market import PricePoint, Quote
from financial_historian.models import Company, CoverageRecord, Fact, StatementBundle, StatementRow
from financial_historian.universe import UniverseMember, UniverseSnapshot

CONTACT = "Offline Fixture offline@example.invalid"
COMPANY = Company("0000000001", "Fictional UI Fixture", "FIX")


class FixtureHistorian:
    fail_search = fail_resolve = fail_generate = empty = False
    periods = 1
    generate_calls = resolve_calls = 0
    search_queries = []

    def __init__(self, user_agent, cache_dir):
        self.user_agent = user_agent

    def search_companies(self, query):
        type(self).search_queries.append(query)
        if self.fail_search:
            raise ValueError(f"Private fixture error {self.user_agent}")
        return [] if query == "NONE" else [COMPANY]

    def resolve_company(self, company):
        type(self).resolve_calls += 1
        if self.fail_resolve:
            raise ValueError(f"Private fixture resolution {self.user_agent}")
        return COMPANY

    def generate(self, company, progress=None):
        type(self).generate_calls += 1
        if progress:
            progress("Reading offline SEC fixture")
        if self.fail_generate:
            raise ValueError(f"Private fixture generation {self.user_agent}")
        bundle = StatementBundle(company)
        row = StatementRow("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "Capital expenditures", "USD")
        for year in range(2025 - self.periods, 2025):
            source = f"https://www.sec.gov/Archives/edgar/data/1/0000000001{year % 100:02}000001/fixture.htm"
            accession = f"0000000001-{year % 100:02}-000001"
            period = f"{year}-12-31"
            coverage = CoverageRecord(accession, period, f"{year + 1}-02-01", source, "fixture", "Offline test only")
            bundle.coverage.append(coverage)
            bundle.periods.append(period)
            if self.empty:
                continue
            fact = Fact(row.tag, row.label, row.unit, 1_200_000, f"{year}-01-01", period,
                        accession, coverage.filed, "10-K", source, "Cash Flow", presentation_value=-1_200_000)
            row.values[period] = fact
            bundle.raw_facts.append(fact)
        if row.values:
            bundle.statements["Cash Flow"] = [row]
        return bundle


class FixtureMarket:
    fail = False
    points = 2
    calls = []

    def quote(self, ticker, period="1y", *, force_refresh=False):
        type(self).calls.append((ticker, period, force_refresh))
        if self.fail:
            raise TimeoutError("Private technical provider error")
        return Quote(ticker, 102.0, 2.0, 2.0,
                     (PricePoint("2025-01-02", 100.0), PricePoint("2025-01-03", 102.0))[:self.points],
                     "Yahoo Finance", datetime.now(timezone.utc).isoformat(), "America/New_York",
                     "latest available close", as_of="2025-01-03", currency="USD")


class FixtureUniverse:
    fail = False
    calls = 0

    def load(self, **kwargs):
        type(self).calls += 1
        if self.fail:
            raise TimeoutError("Private universe failure")
        retrieved = "2025-01-03T12:00:00+00:00"
        return UniverseSnapshot(
            members=(UniverseMember(Company("", COMPANY.name, COMPANY.ticker), ("S&P 500", "Nasdaq-100"),
                                    "https://finance.yahoo.com/", retrieved),),
            retrieved_at=retrieved, checked_at=retrieved,
        )
