"""Company search and retrieval of every available SEC annual filing."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import re
from urllib.parse import quote

from .extract import assemble_bundle, parse_company_facts, parse_filing_html
from .models import Company, CoverageRecord, Filing, STATEMENTS, StatementBundle
from .sec_client import SecAccessError, SecClient

ANNUAL_FORMS = {"10-K", "10-K/A", "10-K405", "10-K405/A", "10-KT", "10-KT/A",
                "20-F", "20-F/A", "40-F", "40-F/A"}


class FinancialHistorian:
    def __init__(self, user_agent: str, cache_dir: Path | None = None):
        self.client = SecClient(user_agent, cache_dir)

    def search_companies(self, query: str) -> list[Company]:
        q = re.sub(r"\s+", " ", query).strip().casefold()
        if len(q) < 1:
            return []
        identifier = q.removeprefix("cik").strip()
        if re.fullmatch(r"\d{1,10}", identifier):
            # The ticker directory omits some delisted/older issuers. A known CIK
            # still resolves directly to the issuer's complete submissions.
            cik = identifier.zfill(10)
            payload = self.client.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", refresh=True)
            if not payload.get("name"):
                return []
            tickers = payload.get("tickers", [])
            return [Company(cik, str(payload["name"]), str(tickers[0]) if tickers else "")]
        payload = self.client.get_json("https://www.sec.gov/files/company_tickers.json")
        result = []
        for record in payload.values():
            if not isinstance(record, dict):
                continue
            name = str(record.get("title", ""))
            ticker = str(record.get("ticker", ""))
            cik = str(record.get("cik_str", "")).zfill(10)
            if not cik.isdigit() or not name:
                continue
            if q in name.casefold() or q in ticker.casefold() or q.lstrip("0") == cik.lstrip("0"):
                rank = (0 if q == ticker.casefold() else
                        1 if ticker.casefold().startswith(q) else
                        2 if name.casefold().startswith(q) else 3)
                result.append((rank, name, Company(cik, name, ticker)))
        return [company for _, _, company in sorted(result, key=lambda x: (x[0], x[1], x[2].ticker))[:30]]

    @staticmethod
    def _filings(block: dict, cik: str) -> list[Filing]:
        records = []
        accessions = block.get("accessionNumber", [])
        for i, accession in enumerate(accessions):
            def at(key: str) -> str:
                values = block.get(key, [])
                return str(values[i] or "") if i < len(values) else ""
            form = at("form")
            if form not in ANNUAL_FORMS or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                continue
            document = at("primaryDocument")
            base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
            if document and "/" not in document and "\\" not in document and document not in {".", ".."}:
                url = base + quote(document, safe="-_.")
            else:
                # A missing document is not silently guessed: source is the filing index.
                document = ""
                url = base + accession + "-index.html"
            records.append(Filing(accession, form, at("filingDate"), at("reportDate"), document, url))
        return records

    def annual_filings(self, company: Company, progress: Callable[[str], None]) -> list[Filing]:
        if not re.fullmatch(r"\d{1,10}", company.cik):
            raise ValueError("Invalid company identifier.")
        cik = company.cik.zfill(10)
        data = self.client.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", refresh=True)
        section = data.get("filings", {})
        records = self._filings(section.get("recent", {}), cik)
        shards = section.get("files", [])
        for i, shard in enumerate(shards):
            name = shard.get("name", "")
            if not re.fullmatch(r"CIK\d{10}-submissions-\d+\.json", name):
                raise SecAccessError("The SEC supplied an unexpected historical-file name; retrieval stopped safely.")
            progress(f"Reading historical filing index {i + 1} of {len(shards)}…")
            historical = self.client.get_json(f"https://data.sec.gov/submissions/{name}", refresh=True)
            records.extend(self._filings(historical, cik))
        deduped = {f.accession: f for f in records}
        return sorted(deduped.values(), key=lambda f: (f.filed, f.accession))

    def generate(self, company: Company, progress: Callable[[str], None] | None = None) -> StatementBundle:
        report = progress or (lambda _: None)
        report("Finding all available annual filings; no year limit…")
        filings = self.annual_filings(company, report)
        if not filings:
            raise ValueError("No supported annual SEC filings were found for this company. "
                             "Search an operating company that files annual reports, rather than a fund or ETF.")
        warnings = [
            "Coverage is all available annual filings for this SEC company identifier, not guaranteed lifetime history. "
            "EDGAR generally starts in the 1990s; older paper reports and predecessor identifiers may require manual research.",
            "Values use the latest available annual filing for each reported tag and period. "
            "Later comparative figures are not automatically proven restatements; changes are flagged for review.",
            "Different tags and units are kept separate. Selected annual period starts are recorded in the sources. "
            "Blank cells mean unavailable observations, never zero. Fiscal-year and accounting changes require analyst review.",
        ]
        facts = []
        facts_warning = ""
        try:
            report("Loading SEC structured financial data…")
            payload = self.client.get_json(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company.cik.zfill(10)}.json", refresh=True)
            facts.extend(parse_company_facts(payload, filings))
        except SecAccessError as exc:
            facts_warning = f"Structured company-facts data could not be loaded: {exc}"
            warnings.append(facts_warning)
        coverage = []
        for index, filing in enumerate(filings):
            report(f"Reading annual filing {index + 1} of {len(filings)} · {filing.report_date or filing.filed} · {filing.form}…")
            extracted = []
            problem = ""
            if not filing.primary_document:
                problem = "No primary document is supplied by the SEC index; review the filing manually."
            else:
                try:
                    document = self.client.get_bytes(filing.source_url, ttl=30 * 86400)
                    extracted = parse_filing_html(document, filing)
                    facts.extend(extracted)
                except SecAccessError as exc:
                    problem = str(exc)
                except (ValueError, TypeError) as exc:
                    # Parsing anomalies get their own coverage record. Never turn them into zeroes.
                    problem = "The filing's statement format could not be interpreted safely; review it manually."
            fallback = [f for f in facts if f.accession == filing.accession and f.extraction == "companyfacts"]
            found = {f.statement for f in extracted}
            fallback_found = {f.statement for f in fallback}
            if found == set(STATEMENTS):
                status = "extracted"
                detail = f"Tagged primary statement observations: {len(extracted)}."
            elif extracted:
                status = "partial"
                detail = f"Tagged statements: {', '.join(sorted(found))}. Other items may use standard SEC facts."
            elif fallback:
                status = "structured fallback"
                detail = (f"Standard company-facts observations: {len(fallback)}; "
                          "company-specific detail could not be recovered from this filing.")
            else:
                status = "unsupported"
                detail = "No trustworthy annual statement values could be extracted; manual review needed."
            if problem:
                detail += " " + problem
            available = found | fallback_found
            if available != set(STATEMENTS):
                missing = set(STATEMENTS) - available
                detail += f" Missing statements: {', '.join(sorted(missing))}."
            coverage.append(CoverageRecord(filing.accession, filing.report_date, filing.filed,
                                           filing.source_url, status, detail))
        bundle = assemble_bundle(company, filings, facts, coverage, warnings)
        missing = sum(c.status in {"unsupported", "partial", "structured fallback"} for c in coverage)
        if missing:
            bundle.warnings.append(f"{missing} of {len(filings)} filings have limited extraction. "
                                   "Read Sources & Coverage before using these statements in a model.")
        if not bundle.raw_facts:
            # A coverage-only workbook is useful, but make its lack of values explicit.
            bundle.warnings.append("No financial values were extracted. This workbook contains filing links and coverage only.")
        report("Preparing statement rows and source records…")
        return bundle
