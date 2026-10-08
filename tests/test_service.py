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


def test_invalid_kpi_registry_does_not_block_financial_retrieval(monkeypatch):
    import financial_historian.operating_kpis as registry
    def invalid(*args):
        raise ValueError("private untrusted registry detail")
    monkeypatch.setattr(registry, "load_kpi_mappings", invalid)
    record=filing_record(2023,1)
    client=FixtureClient({
        SUBMISSIONS:{"filings":{"recent":columnar([record]),"files":[]}},
        FACTS:{"cik":1,"facts":{}},
    })
    monkeypatch.setattr(service,"parse_filing_html",lambda content,filing:[observation(filing)])
    result=historian(client).generate(COMPANY)
    assert result.raw_facts
    assert any("KPI configuration could not be validated" in warning for warning in result.warnings)
    assert all("private untrusted" not in warning for warning in result.warnings)


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
    client = FixtureClient({SUBMISSIONS: {"cik": 1, "name": "Former Listed Company", "tickers": []}})
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
    assert bundle.coverage[0].status == "partial"
    assert "Core rows not verified" in bundle.coverage[0].detail
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
    assert bundle.periods == ["2023-12-31"]  # Discovered but unsupported periods stay visibly blank.
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
    assert "Filing index checked" in bundle.coverage[0].detail
    assert "Balance Sheet" in bundle.coverage[0].detail
    assert "Cash Flow" in bundle.coverage[0].detail
    assert len(bundle.raw_facts) == 1
    assert len(client.document_calls) == 1
    assert client.document_calls[0][0].endswith("-index.html")


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
    assert [item.status for item in bundle.coverage] == ["unsupported", "partial"]
    assert len(client.document_calls) == 2
    assert "interpreted safely" in bundle.coverage[0].detail
    assert len(bundle.raw_facts) == 3


def test_complete_primary_statements_need_core_rows_and_balanced_totals(monkeypatch, capture_assembly):
    record = filing_record(2023, 1)
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar([record])}}, FACTS: {}})
    monkeypatch.setattr(service, "parse_company_facts", lambda *_: [])

    def parse(_, filing):
        totals = [
            (STATEMENTS[0], "Revenues", 100), (STATEMENTS[0], "NetIncomeLoss", 10),
            (STATEMENTS[1], "Assets", 60), (STATEMENTS[1], "Liabilities", 40),
            (STATEMENTS[1], "StockholdersEquity", 20),
            (STATEMENTS[2], "NetCashProvidedByUsedInOperatingActivities", 20),
            (STATEMENTS[2], "NetCashProvidedByUsedInInvestingActivities", -10),
            (STATEMENTS[2], "NetCashProvidedByUsedInFinancingActivities", -8),
        ]
        return [Fact("us-gaap:" + tag, tag, "USD", value,
                     None if statement == STATEMENTS[1] else "2023-01-01", "2023-12-31",
                     filing.accession, filing.filed, filing.form, filing.source_url,
                     statement, "inline-xbrl") for statement, tag, value in totals]

    monkeypatch.setattr(service, "parse_filing_html", parse)
    bundle = historian(client).generate(COMPANY)
    assert bundle.coverage[0].status == "extracted"
    assert "Core statement checks passed" in bundle.coverage[0].detail


def test_assembly_progress_precedes_assembly_work(monkeypatch):
    record = filing_record(2023, 1)
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar([record])}}, FACTS: {}})
    monkeypatch.setattr(service, "parse_company_facts", lambda *_: [])
    monkeypatch.setattr(service, "parse_filing_html", lambda *_: [])
    progress = []

    def assemble(company, filings, facts, coverage, warnings):
        assert progress[-1] == "Preparing statement rows and source records…"
        return StatementBundle(company)

    monkeypatch.setattr(service, "assemble_bundle", assemble)
    historian(client).generate(COMPANY, progress.append)


def test_unexpected_programming_failure_is_not_reported_as_unsupported_filing(monkeypatch):
    record = filing_record(2023, 1)
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar([record])}}, FACTS: {}})
    monkeypatch.setattr(service, "parse_company_facts", lambda *_: [])

    def parse(*_):
        raise TypeError("Unexpected programming failure")

    monkeypatch.setattr(service, "parse_filing_html", parse)
    with pytest.raises(TypeError, match="programming failure"):
        historian(client).generate(COMPANY)


@pytest.mark.parametrize("actual", [2, "0000000002", None, "1.0", 0, "12345678901"])
def test_direct_cik_search_rejects_mismatched_or_invalid_sec_identifier(actual):
    client = FixtureClient({SUBMISSIONS: {"cik": actual, "name": "Wrong issuer", "tickers": []}})
    with pytest.raises(SecAccessError, match="identifier"):
        historian(client).search_companies("1")
    assert not client.document_calls


def test_yahoo_share_class_symbol_resolves_exact_sec_ticker_and_profile():
    client = FixtureClient({
        "https://www.sec.gov/files/company_tickers.json": {
            "0": {"cik_str": 1, "title": "Directory name", "ticker": "BRK.B"},
            "1": {"cik_str": 2, "title": "BRK-B named unrelated issuer", "ticker": "OTHER"}},
        SUBMISSIONS: {"cik": "0000000001", "name": "SEC verified issuer", "tickers": ["BRK.A", "BRK.B"]}})
    company = historian(client).resolve_company(Company("", "Untrusted market name", "BRK-B"))
    assert company == Company("0000000001", "SEC verified issuer", "BRK.B")
    assert not client.document_calls


def test_ticker_name_substring_is_not_an_identity_match():
    client = FixtureClient({"https://www.sec.gov/files/company_tickers.json": {
        "0": {"cik_str": 1, "title": "ABC Holdings", "ticker": "ABCD"}}})
    with pytest.raises(SecAccessError, match="unambiguously"):
        historian(client).resolve_company(Company("", "Yahoo name", "ABC"))
    assert len(client.json_calls) == 1


def test_resolve_rejects_cik_ticker_cross_issuer_mismatch():
    client = FixtureClient({SUBMISSIONS: {"cik": 1, "name": "Issuer One", "tickers": ["ONE"]}})
    with pytest.raises(SecAccessError, match="not associated"):
        historian(client).resolve_company(Company("1", "Ignored", "OTHER"))
    assert not client.document_calls


def test_cik_only_resolves_delisted_issuer_without_a_market_ticker():
    client = FixtureClient({SUBMISSIONS: {"cik": 1, "name": "Former issuer", "tickers": []}})
    assert historian(client).resolve_company(Company("1", "")) == Company("0000000001", "Former issuer")


@pytest.mark.parametrize("cik", ["0", "0000000000", "1.0", "12345678901", "../1", "١"])
def test_resolve_rejects_invalid_cik_without_network(cik):
    client = FixtureClient()
    with pytest.raises(ValueError, match="identifier"):
        historian(client).resolve_company(Company(cik, "Invalid"))
    assert not client.json_calls


def test_historical_shard_must_belong_to_validated_company():
    client = FixtureClient({SUBMISSIONS: {"filings": {"files": [{"name": "CIK0000000002-submissions-001.json"}]}}})
    with pytest.raises(SecAccessError, match="historical-file"):
        historian(client).annual_filings(COMPANY, lambda _: None)
    assert len(client.json_calls) == 1


def test_generate_retrieves_only_latest_twenty_period_documents_but_keeps_amendments_and_raw(monkeypatch, capture_assembly):
    records = [filing_record(year, year - 1999) for year in range(2000, 2026)]
    records.append(filing_record(2025, 99, "10-K/A"))
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar(records)}}, FACTS: {}})
    raw = []

    def structured(_, filings):
        for filing in filings:
            fact = observation(filing, extraction="companyfacts")
            raw.append(service.replace(fact, end=filing.report_date, start=filing.report_date[:4] + "-01-01"))
        return raw

    monkeypatch.setattr(service, "parse_company_facts", structured)
    monkeypatch.setattr(service, "parse_filing_html", lambda *_: [])
    bundle = historian(client).generate(COMPANY)
    assert len(client.document_calls) == 22  # Twenty displayed periods, one lookback, plus amendment.
    assert len(bundle.filings) == 27
    assert len(bundle.raw_facts) == 27
    assert bundle.periods == [f"{year}-12-31" for year in range(2025, 2005, -1)]
    outside = [item for item in bundle.coverage if item.status == "outside presentation window"]
    assert len(outside) == 5
    assert all(item.report_date < "2006-01-01" for item in outside)
    assert all("not retrieved" in item.detail for item in outside)


def test_unknown_fiscal_period_is_explicit_not_guessed_or_fetched(monkeypatch, capture_assembly):
    records = [filing_record(2025, 1), dict(filing_record(2024, 2), reportDate="")]
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar(records)}}, FACTS: {}})
    monkeypatch.setattr(service, "parse_company_facts", lambda *_: [])
    monkeypatch.setattr(service, "parse_filing_html", lambda *_: [])
    bundle = historian(client).generate(COMPANY)
    assert len(client.document_calls) == 1
    assert any("guessed period" in item.detail for item in bundle.coverage)


def test_company_facts_mismatched_identifier_is_never_parsed(monkeypatch, capture_assembly):
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar([filing_record(2025, 1)])}},
                            FACTS: {"cik": 2, "facts": {}}})
    calls = []
    monkeypatch.setattr(service, "parse_company_facts", lambda *args: calls.append(args) or [])
    monkeypatch.setattr(service, "parse_filing_html", lambda *_: [])
    bundle = historian(client).generate(COMPANY)
    assert calls == []
    assert any("identifier does not match" in warning for warning in bundle.warnings)


def test_missing_primary_index_document_failure_is_a_failed_refresh(monkeypatch, capture_assembly):
    record = filing_record(2025, 1, document="")
    filing = service.FinancialHistorian._filings(columnar([record]), COMPANY.cik)[0]
    source = filing.source_url.rsplit("/", 1)[0] + "/annual.htm"
    index = (b'<table><tr><th>Type</th><th>Document</th><th>Seq</th></tr>'
             b'<tr><td>10-K</td><td><a href="annual.htm">Annual</a></td><td>1</td></tr></table>')
    client = FixtureClient({SUBMISSIONS: {"filings": {"recent": columnar([record])}}, FACTS: {}},
                           {filing.source_url: index, source: SecAccessError("SEC unavailable")})
    monkeypatch.setattr(service, "parse_company_facts", lambda *_: [])
    bundle = historian(client).generate(COMPANY)
    assert any(warning.startswith("One or more SEC filing documents could not be retrieved;")
               for warning in bundle.warnings)
