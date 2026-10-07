"""Service checks use local SEC-shaped fixtures, never live SEC requests."""
from __future__ import annotations

import pytest

from financial_historian import service
from financial_historian.models import Company, Fact, STATEMENTS, StatementBundle
from financial_historian.sec_client import SecAccessError


COMPANY = Company("0000000001", "Example Manufacturing", "EXM")
SUBMISSIONS = "https://data.sec.gov/submissions/CIK0000000001.json"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"


def filing_record(year, sequence, form="10-K", document="annual.htm"):
    return {
        "accessionNumber": f"0000000001-{year % 100:02d}-{sequence:06d}",
        "form": form,
        "filingDate": f"{year + 1}-02-15",
        "reportDate": f"{year}-12-31",
        "primaryDocument": document,
    }


def columnar(records):
    return {key: [r.get(key, "") for r in records] for key in (
        "accessionNumber", "form", "filingDate", "reportDate", "primaryDocument"
    )}


class FixtureClient:
    def __init__(self, json_payloads=None, documents=None):
        self.json_payloads = json_payloads or {}
        self.documents = documents or {}
        self.json_calls = []
        self.document_calls = []

    def get_json(self, url, **kwargs):
        self.json_calls.append((url, kwargs))
        result = self.json_payloads[url]
        if isinstance(result, Exception):
            raise result
        return result

    def get_bytes(self, url, **kwargs):
        self.document_calls.append((url, kwargs))
        result = self.documents.get(url, b"fixture statement")
        if isinstance(result, Exception):
            raise result
        return result


def historian(client):
    instance = service.FinancialHistorian.__new__(service.FinancialHistorian)
    instance.client = client
    return instance


def observation(filing, statement=STATEMENTS[0], extraction="inline-xbrl"):
    return Fact("ex:ReportedValue", "Reported value", "USD", 123.0,
                "2023-01-01", "2023-12-31", filing.accession, filing.filed,
                filing.form, filing.source_url, statement, extraction)


@pytest.fixture
def capture_assembly(monkeypatch):
    """Expose service orchestration independently of the extraction algorithm."""
    captured = {}

    def assemble(company, filings, facts, coverage, warnings):
        captured.update(facts=list(facts), filings=list(filings), coverage=list(coverage))
        return StatementBundle(company, periods=sorted({f.end for f in facts}),
                               raw_facts=list(facts), filings=list(filings),
                               coverage=list(coverage), warnings=list(warnings))

    monkeypatch.setattr(service, "assemble_bundle", assemble)
    return captured


def test_reads_every_historical_shard_without_fifty_year_cap_or_quarterlies():
    annuals = [filing_record(year, i) for i, year in enumerate(range(1950, 2015), 1)]
    amendment = filing_record(2014, 70, "10-K/A")
    quarterly = filing_record(2014, 71, "10-Q")
    shard_names = [f"CIK0000000001-submissions-{i:03d}.json" for i in range(1, 4)]
    payloads = {
        SUBMISSIONS: {"filings": {"recent": columnar([annuals[-1], amendment, quarterly]),
                                 "files": [{"name": name} for name in shard_names]}},
    }
    for name, records in zip(shard_names, [annuals[:25], annuals[25:50], annuals[50:]]):
        payloads[f"https://data.sec.gov/submissions/{name}"] = columnar(records)
    client = FixtureClient(payloads)
    progress = []
    filings = historian(client).annual_filings(COMPANY, progress.append)

    assert len(filings) == 66  # 65 annual years, plus a distinct amendment.
    assert {f.report_date for f in filings} == {f"{year}-12-31" for year in range(1950, 2015)}
    assert len({f.accession for f in filings}) == len(filings)
    assert {f.form for f in filings} == {"10-K", "10-K/A"}
    assert filings[0].report_date == "1950-12-31"
    assert len(client.json_calls) == 4
    assert all(kwargs.get("refresh") is True for _, kwargs in client.json_calls)
    assert len(progress) == 3


def test_exact_ticker_ranks_ahead_of_name_and_prefix_matches():
    data = {
        "0": {"title": "AA Machinery", "ticker": "AAPLX", "cik_str": 2},
        "1": {"title": "Zeta Devices", "ticker": "AAPL", "cik_str": 1},
        "2": {"title": "AAPL Products", "ticker": "OTHER", "cik_str": 3},
        "3": {"title": "Unrelated", "ticker": "XYZ", "cik_str": 4},
    }
    client = FixtureClient({"https://www.sec.gov/files/company_tickers.json": data})
    result = historian(client).search_companies("  aaPL  ")
    assert [company.ticker for company in result] == ["AAPL", "AAPLX", "OTHER"]
    assert result[0].cik == "0000000001"


def test_blank_search_needs_no_sec_request():
    client = FixtureClient()
    assert historian(client).search_companies(" \t ") == []
    assert not client.json_calls


@pytest.mark.parametrize("query", ["1", "0000000001", "CIK 0000000001", "cik1"])
def test_known_cik_resolves_older_issuer_even_without_current_ticker_listing(query):
    client = FixtureClient({SUBMISSIONS: {"name": "Former Listed Company", "tickers": []}})
    assert historian(client).search_companies(query) == [
        Company("0000000001", "Former Listed Company", "")
    ]
    assert client.json_calls == [(SUBMISSIONS, {"refresh": True})]


@pytest.mark.parametrize("document", ["", "../annual.htm", "folder/annual.htm", "folder\\annual.htm"])
def test_missing_or_unsafe_primary_document_preserves_filing_index_provenance(document):
    record = filing_record(2023, 1, document=document)
    filings = service.FinancialHistorian._filings(columnar([record]), COMPANY.cik)
    assert len(filings) == 1
    filing = filings[0]
    assert filing.primary_document == ""
    assert filing.source_url.endswith(f"/{filing.accession}-index.html")


@pytest.mark.parametrize("bad_name", ["../private.json", "https://other.test/index.json", "CIK1-submissions-1.json"])
def test_unexpected_historical_path_stops_before_following_it(bad_name):
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": {}, "files": [{"name": bad_name}]}}})
    with pytest.raises(SecAccessError, match="historical-file"):
        historian(client).annual_filings(COMPANY, lambda _: None)
    assert len(client.json_calls) == 1


def test_invalid_cik_stops_before_request():
    client = FixtureClient()
    with pytest.raises(ValueError, match="identifier"):
        historian(client).annual_filings(Company("../../1", "Invalid"), lambda _: None)
    assert not client.json_calls


def test_no_supported_filings_is_actionable_and_does_not_invent_results():
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar([filing_record(2023, 1, "10-Q")])}}})
    with pytest.raises(ValueError, match="No supported annual SEC filings"):
        historian(client).generate(COMPANY)
    assert not client.document_calls


def test_failed_structured_data_still_extracts_filing_and_records_warning(monkeypatch, capture_assembly):
    record = filing_record(2023, 1)
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar([record])}},
                            FACTS: SecAccessError("SEC temporarily unavailable")})
    monkeypatch.setattr(service, "parse_filing_html", lambda _, filing: [
        observation(filing, statement) for statement in STATEMENTS
    ])
    bundle = historian(client).generate(COMPANY)
    assert bundle.coverage[0].status == "extracted"
    assert len(bundle.raw_facts) == 3
    assert any("Structured company-facts data could not be loaded" in w for w in bundle.warnings)
    assert dict(client.json_calls)[FACTS]["refresh"] is True


def test_inaccessible_filing_retains_coverage_without_fabricating_values(monkeypatch, capture_assembly):
    record = filing_record(2023, 1)
    filing = service.FinancialHistorian._filings(columnar([record]), COMPANY.cik)[0]
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar([record])}}, FACTS: {}},
                            {filing.source_url: SecAccessError("The requested SEC record is unavailable (404).")})
    monkeypatch.setattr(service, "parse_company_facts", lambda *_: [])
    bundle = historian(client).generate(COMPANY)
    assert bundle.periods == []
    assert bundle.raw_facts == []
    assert bundle.coverage[0].status == "unsupported"
    assert bundle.coverage[0].source_url == filing.source_url
    assert "404" in bundle.coverage[0].detail
    assert all(statement == [] for statement in bundle.statements.values())
    assert any("No financial values were extracted" in w for w in bundle.warnings)


def test_structured_fallback_is_explicit_and_preserves_missing_statement_warning(monkeypatch, capture_assembly):
    record = filing_record(2023, 1, document="")
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar([record])}}, FACTS: {}})
    monkeypatch.setattr(service, "parse_company_facts", lambda _, filings: [
        observation(filings[0], STATEMENTS[0], extraction="companyfacts")
    ])
    bundle = historian(client).generate(COMPANY)
    assert bundle.coverage[0].status == "structured fallback"
    assert "No primary document" in bundle.coverage[0].detail
    assert "Balance Sheet" in bundle.coverage[0].detail
    assert "Cash Flow" in bundle.coverage[0].detail
    assert len(bundle.raw_facts) == 1
    assert not client.document_calls


def test_parser_failure_is_coverage_gap_and_next_filing_is_still_processed(monkeypatch, capture_assembly):
    records = [filing_record(2022, 1), filing_record(2023, 2)]
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar(records)}}, FACTS: {}})
    monkeypatch.setattr(service, "parse_company_facts", lambda *_: [])

    def parse(_, filing):
        if filing.report_date == "2022-12-31":
            raise ValueError("Broken statement markup")
        return [observation(filing, statement) for statement in STATEMENTS]

    monkeypatch.setattr(service, "parse_filing_html", parse)
    bundle = historian(client).generate(COMPANY)
    assert [item.status for item in bundle.coverage] == ["unsupported", "extracted"]
    assert len(client.document_calls) == 2
    assert "interpreted safely" in bundle.coverage[0].detail
    assert len(bundle.raw_facts) == 3
