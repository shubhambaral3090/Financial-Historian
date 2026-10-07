"""Historical index discovery uses local SEC-shaped fixtures only."""
from dataclasses import replace

import pytest

from financial_historian import service
from financial_historian.models import Company, Fact, Filing
from financial_historian.sec_client import SecAccessError


ACCESSION = "0000000001-94-000001"
BASE = "https://www.sec.gov/Archives/edgar/data/1/000000000194000001/"
INDEX = BASE + ACCESSION + "-index.html"
COMPLETE = "https://www.sec.gov/Archives/edgar/data/1/" + ACCESSION + ".txt"
FILING = Filing(ACCESSION, "10-K", "1995-02-01", "1994-12-31", "", INDEX)
ANNUAL_HTML = b"<html><body><h1>Consolidated statements of operations</h1></body></html>"


def index_page(*rows, complete=False):
    rows = "".join(f'<tr><td>{i}</td><td>Document</td><td><a href="{url}">File</a></td>'
                   f'<td>{form}</td><td>123</td></tr>' for i, form, url in rows)
    ending = f'<a href="{COMPLETE}">Complete submission text file</a>' if complete else ""
    return ('<html><table class="tableFile"><tr><th>Seq</th><th>Description</th>'
            '<th>Document</th><th>Type</th><th>Size</th></tr>' + rows + '</table>'
            + ending + '</html>').encode()


class ArchiveClient:
    def __init__(self, documents):
        self.documents = documents
        self.calls = []

    def get_bytes(self, url, **kwargs):
        self.calls.append(url)
        result = self.documents[url]
        if isinstance(result, Exception):
            raise result
        return result


def archive_reader(documents):
    instance = service.FinancialHistorian.__new__(service.FinancialHistorian)
    instance.client = ArchiveClient(documents)
    return instance


def test_missing_primary_uses_exact_annual_type_not_exhibit_or_amendment():
    url = BASE + "annual.htm"
    reader = archive_reader({
        INDEX: index_page((1, "EX-13", BASE + "exhibit.htm"),
                          (2, "10-K/A", BASE + "amendment.htm"), (3, "10-K", url)),
        url: ANNUAL_HTML,
    })
    resolved, document, note = reader._filing_document(FILING)
    assert resolved == replace(FILING, primary_document="annual.htm", source_url=url)
    assert document == ANNUAL_HTML
    assert reader.client.calls == [INDEX, url]
    assert "located through the SEC filing index" in note


def test_primary_match_obeys_actual_type_header_position():
    body = ('<table><tr><th>Type</th><th>Document</th><th>Seq</th></tr>'
            '<tr><td>10-K</td><td><a href="annual.htm">Annual</a></td><td>1</td></tr></table>').encode()
    primary, complete = service._index_documents(body, FILING)
    assert primary == [BASE + "annual.htm"]
    assert complete == []


@pytest.mark.parametrize("href", [
    "https://evil.example/annual.htm", "http://www.sec.gov/annual.htm",
    "https://data.sec.gov/Archives/edgar/data/1/000000000194000001/annual.htm",
    "https://user:password@www.sec.gov/Archives/edgar/data/1/000000000194000001/annual.htm",
    "../other-accession/annual.htm", "../annual.htm", "%2e%2e/annual.htm",
    "%2f..%2fother-accession/annual.htm", "annual.htm?redirect=other", "annual.htm#other",
    "https://www.sec.gov:bad/annual.htm", "//evil.example/annual.htm", "javascript:alert(1)",
])
def test_unrelated_or_unsafe_index_links_are_never_requested(href):
    reader = archive_reader({INDEX: index_page((1, "10-K", href))})
    resolved, document, note = reader._filing_document(FILING)
    assert resolved == FILING
    assert document is None
    assert reader.client.calls == [INDEX]
    assert "Filing index checked" in note


def test_complete_submission_extracts_only_exact_annual_document_block():
    complete = (b"<SEC-DOCUMENT><DOCUMENT><TYPE>EX-13\n<TEXT><html>Wrong exhibit</html></TEXT></DOCUMENT>"
                b"<DOCUMENT><TYPE>10-K/A\n<TEXT><html>Wrong amendment</html></TEXT></DOCUMENT>"
                b"<DOCUMENT><TYPE>10-K\n<FILENAME>annual.htm\n<TEXT>" + ANNUAL_HTML
                + b"</TEXT></DOCUMENT></SEC-DOCUMENT>")
    reader = archive_reader({INDEX: index_page(complete=True), COMPLETE: complete})
    resolved, document, note = reader._filing_document(FILING)
    assert document == ANNUAL_HTML
    assert resolved.primary_document == ACCESSION + ".txt"
    assert resolved.source_url == COMPLETE
    assert "inside the SEC complete submission" in note
    assert reader.client.calls == [INDEX, COMPLETE]


def test_plain_text_annual_block_does_not_extract_html_exhibit():
    complete = (b"<DOCUMENT><TYPE>10-K\n<TEXT>Annual ASCII report\n<TABLE><S><C>123</TABLE>"
                b"</TEXT></DOCUMENT><DOCUMENT><TYPE>EX-13\n<TEXT>" + ANNUAL_HTML
                + b"</TEXT></DOCUMENT>")
    reader = archive_reader({INDEX: index_page(complete=True), COMPLETE: complete})
    resolved, document, note = reader._filing_document(FILING)
    assert resolved.source_url == COMPLETE
    assert document is None
    assert "Complete submission checked" in note
    assert "plain-text statements need manual extraction" in note


def test_plain_text_primary_is_read_and_labeled_unsupported():
    url = BASE + "annual.txt"
    reader = archive_reader({INDEX: index_page((1, "10-K", url)), url: b"ASCII annual report"})
    resolved, document, note = reader._filing_document(FILING)
    assert resolved.source_url == url
    assert document is None
    assert "located" in note and "plain-text format is not supported" in note
    assert reader.client.calls == [INDEX, url]


def test_inaccessible_index_reports_sec_error_without_guessing_document_paths():
    reader = archive_reader({INDEX: SecAccessError("SEC unavailable")})
    with pytest.raises(SecAccessError, match="SEC unavailable"):
        reader._filing_document(FILING)
    assert reader.client.calls == [INDEX]


def test_inaccessible_primary_can_use_a_listed_complete_submission():
    url = BASE + "annual.htm"
    reader = archive_reader({
        INDEX: index_page((1, "10-K", url), complete=True),
        url: SecAccessError("SEC record unavailable (404)"),
        COMPLETE: b"<DOCUMENT><TYPE>10-K\n<TEXT>" + ANNUAL_HTML + b"</TEXT></DOCUMENT>",
    })
    resolved, document, _ = reader._filing_document(FILING)
    assert resolved.source_url == COMPLETE
    assert document == ANNUAL_HTML
    assert reader.client.calls == [INDEX, url, COMPLETE]


def test_complete_submission_link_must_name_this_exact_accession():
    other = COMPLETE.replace("94-000001", "94-000002")
    body = f'<a href="{other}">Complete submission text file</a>'.encode()
    assert service._index_documents(body, FILING) == ([], [])


def test_generate_updates_filing_and_fact_provenance_after_discovery(monkeypatch):
    url = BASE + "annual.htm"
    reader = archive_reader({INDEX: index_page((1, "10-K", url)), url: ANNUAL_HTML})
    reader.client.get_json = lambda *_args, **_kwargs: {}
    monkeypatch.setattr(reader, "annual_filings", lambda *_args: [FILING])
    monkeypatch.setattr(service, "parse_company_facts", lambda *_args: [])

    def parse(document, filing):
        assert document == ANNUAL_HTML
        assert filing.source_url == url
        return [Fact("us-gaap:Revenues", "Revenue", "USD", 10, "1994-01-01", "1994-12-31",
                     filing.accession, filing.filed, filing.form, filing.source_url,
                     "Profit & Loss", "html-table")]

    monkeypatch.setattr(service, "parse_filing_html", parse)
    bundle = reader.generate(Company("0000000001", "Example", "EX"))
    assert bundle.filings[0].source_url == url
    assert bundle.raw_facts[0].source_url == url
    assert bundle.coverage[0].source_url == url
    assert bundle.coverage[0].status == "partial"
