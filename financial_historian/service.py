"""SEC company validation, filing discovery and twenty-period retrieval."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
import re
from urllib.parse import quote, unquote, urljoin, urlsplit

from lxml import etree, html

from .extract import assemble_bundle, parse_company_facts, parse_filing_html
from .models import Company, CoverageRecord, Filing, STATEMENTS, StatementBundle
from .quality import inspect_bundle, inspect_filing
from .sec_client import SecAccessError, SecClient

ANNUAL_FORMS = {"10-K", "10-K/A", "10-K405", "10-K405/A", "10-KT", "10-KT/A",
                "20-F", "20-F/A", "40-F", "40-F/A"}


def limit_statement_history(bundle: StatementBundle, years: int = 20) -> StatementBundle:
    """Limit displayed statement cells without deleting raw source facts.

    Periods are fiscal period ends, not calendar years. Coverage and raw facts
    remain complete so the workbook can explain what was discovered outside the
    presentation window.
    """
    if isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("History limit must be a positive integer.")
    discovered = {filing.report_date for filing in bundle.filings if _valid_period(filing.report_date)}
    discovered.update(bundle.periods)
    discovered.update(period for rows in bundle.statements.values() for row in rows for period in row.values)
    available = sorted(discovered, reverse=True)
    keep = set(available[:years])
    statements = {
        statement: [replace(row, values={period: fact for period, fact in row.values.items()
                                        if period in keep}, accepted_tags=set(row.accepted_tags))
                    for row in rows]
        for statement, rows in bundle.statements.items()
    }
    warnings = [warning for warning in bundle.warnings
                if not warning.startswith(("Statement presentation is limited to the latest ",
                                           "No verified statement observations are available for fiscal period"))]
    warnings.append(f"Statement presentation is limited to the latest {years} fiscal periods; raw source records and filing coverage remain available for audit.")
    observed = {period for rows in statements.values() for row in rows for period in row.values}
    empty = sorted(keep - observed, reverse=True)
    if empty:
        warnings.append("No verified statement observations are available for fiscal period(s): "
                        + ", ".join(empty) + "; blank columns are intentional.")
    return replace(bundle, periods=sorted(keep, reverse=True), statements=statements,
                   warnings=list(dict.fromkeys(warnings)))


def _valid_period(value: str) -> bool:
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and date.fromisoformat(value) <= date.today()
    except (TypeError, ValueError):
        return False


def normalize_cik(value: object) -> str:
    """Accept only an actual, positive SEC identifier, never a guessed number."""
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]{1,10}", text) or int(text) == 0:
        raise ValueError("Invalid company identifier.")
    return text.zfill(10)


def normalize_ticker(value: str) -> str:
    """Yahoo uses a dash where SEC directories may use a share-class dot."""
    return str(value).strip().upper().replace(".", "-")


def _validate_submissions(payload: object, expected_cik: str, *, require_identity: bool = False) -> None:
    if not isinstance(payload, dict):
        raise SecAccessError("The SEC company profile could not be validated.")
    if require_identity or "cik" in payload:
        try:
            actual = normalize_cik(payload.get("cik", ""))
        except ValueError:
            raise SecAccessError("The SEC company identifier could not be validated.") from None
        if actual != expected_cik:
            raise SecAccessError("The SEC company identifier does not match the selected company.")


def _archive_document_url(index_url: str, href: str, accession: str,
                          *, complete_submission: bool = False) -> str | None:
    """Accept files inside this accession, plus its listed complete submission.

    Historical SEC indexes often link complete submissions one directory above
    the accession folder. That one exact filename is allowed; arbitrary issuer
    paths and links to other filings are never followed.
    """
    try:
        target = urljoin(index_url, href)
        parsed = urlsplit(target)
        origin = urlsplit(index_url)
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.hostname != "www.sec.gov"
            or parsed.username or parsed.password or port not in {None, 443}
            or parsed.query or parsed.fragment):
        return None
    path = unquote(parsed.path)
    accession_dir = origin.path.rsplit("/", 1)[0] + "/"
    # Reject encoded traversal and filenames that normalize to another path.
    if "\\" in path or any(part in {".", ".."} for part in path.split("/")):
        return None
    filename = path.rsplit("/", 1)[-1]
    within_accession = path.rsplit("/", 1)[0] + "/" == accession_dir
    if complete_submission:
        issuer_dir = accession_dir.rstrip("/").rsplit("/", 1)[0] + "/"
        if filename != accession + ".txt" or path not in {
            accession_dir + filename, issuer_dir + filename,
        }:
            return None
    elif not within_accession or not filename or filename.endswith("-index.html"):
        return None
    return target


def _index_documents(document: bytes, filing: Filing) -> tuple[list[str], list[str]]:
    """Read the index's actual document type column, not descriptions or exhibits."""
    try:
        root = html.fromstring(document)
    except etree.ParserError:
        return [], []
    primary = []
    for table in root.xpath("//table"):
        columns = None
        for row in table.xpath("./tr | ./thead/tr | ./tbody/tr"):
            cells = row.xpath("./th | ./td")
            values = [" ".join(cell.itertext()).strip() for cell in cells]
            normalized = [re.sub(r"\s+", " ", value).casefold() for value in values]
            if "type" in normalized and "document" in normalized:
                columns = {name: normalized.index(name) for name in ("type", "document")}
                columns["seq"] = normalized.index("seq") if "seq" in normalized else 0
                continue
            if columns is None or len(cells) <= max(columns.values()):
                continue
            if values[columns["type"]].strip().upper() != filing.form.upper():
                continue
            sequence = values[columns["seq"]]
            rank = int(sequence) if sequence.isdigit() else 999999
            for href in cells[columns["document"]].xpath(".//a/@href"):
                target = _archive_document_url(filing.source_url, href, filing.accession)
                if target and target not in {url for _, url in primary}:
                    primary.append((rank, target))
    complete = []
    for href in root.xpath("//a/@href"):
        target = _archive_document_url(filing.source_url, href, filing.accession,
                                       complete_submission=True)
        if target and target not in complete:
            complete.append(target)
    return [url for _, url in sorted(primary, key=lambda item: item[0])], complete


def _annual_submission_html(document: bytes, form: str) -> bytes | None:
    """Extract only the exact annual form's HTML from an SGML submission."""
    for match in re.finditer(rb"<DOCUMENT\s*>(.*?)</DOCUMENT\s*>", document, re.I | re.S):
        block = match.group(1)
        document_type = re.search(rb"<TYPE>\s*([^\r\n<]+)", block, re.I)
        if document_type is None or document_type.group(1).strip().upper() != form.encode("ascii"):
            continue
        text = re.search(rb"<TEXT\s*>(.*?)</TEXT\s*>", block, re.I | re.S)
        if text is not None and _is_html_statement_document(text.group(1)):
            return text.group(1)
    return None


def _is_html_statement_document(document: bytes) -> bool:
    # Old SGML <TABLE><S><C> ASCII tables are not HTML financial tables.
    return bool(re.search(rb"<html\b|<tr\b[^>]*>\s*<t[dh]\b", document, re.I))


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
            cik = normalize_cik(identifier)
            payload = self.client.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", refresh=True)
            _validate_submissions(payload, cik, require_identity=True)
            if not payload.get("name"):
                return []
            tickers = payload.get("tickers", [])
            return [Company(cik, str(payload["name"]), str(tickers[0]) if tickers else "")]
        payload = self.client.get_json("https://www.sec.gov/files/company_tickers.json")
        if not isinstance(payload, dict):
            raise SecAccessError("The SEC company directory could not be read.")
        result = []
        for record in payload.values():
            if not isinstance(record, dict):
                continue
            name = str(record.get("title", ""))
            ticker = str(record.get("ticker", ""))
            try:
                cik = normalize_cik(record.get("cik_str", ""))
            except ValueError:
                continue
            if not name:
                continue
            exact_ticker = normalize_ticker(q) == normalize_ticker(ticker)
            if exact_ticker or q in name.casefold() or q in ticker.casefold() or q.lstrip("0") == cik.lstrip("0"):
                rank = (0 if exact_ticker else
                        1 if ticker.casefold().startswith(q) else
                        2 if name.casefold().startswith(q) else 3)
                result.append((rank, name, Company(cik, name, ticker)))
        return [company for _, _, company in sorted(result, key=lambda x: (x[0], x[1], x[2].ticker))[:30]]

    def resolve_company(self, selected: Company) -> Company:
        """Resolve Yahoo selections against SEC records before following filings.

        Names supplied by market providers are only display hints. A Yahoo
        ticker must match an SEC ticker exactly (allowing share-class dot/dash)
        and the submissions response must independently confirm the CIK.
        """
        ticker = normalize_ticker(selected.ticker)
        if selected.cik:
            cik = normalize_cik(selected.cik)
        else:
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,19}", ticker):
                raise ValueError("Select a valid ticker or SEC company identifier.")
            matches = {company.cik: company for company in self.search_companies(ticker)
                       if normalize_ticker(company.ticker) == ticker}
            if len(matches) != 1:
                raise SecAccessError("This market ticker could not be matched unambiguously to an SEC company. "
                                     "Try searching by company name or CIK.")
            cik = next(iter(matches))
        payload = self.client.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", refresh=True)
        _validate_submissions(payload, cik, require_identity=True)
        name = payload.get("name")
        tickers = payload.get("tickers", [])
        if not isinstance(name, str) or not name.strip() or not isinstance(tickers, list):
            raise SecAccessError("The SEC company profile could not be validated.")
        official_tickers = [value.strip() for value in tickers if isinstance(value, str) and value.strip()]
        if ticker and ticker not in {normalize_ticker(value) for value in official_tickers}:
            raise SecAccessError("The selected ticker is not associated with this SEC company identifier. "
                                 "Search by company name or CIK to verify the issuer.")
        official = next((value for value in official_tickers if normalize_ticker(value) == ticker),
                        official_tickers[0] if official_tickers else "")
        return Company(cik, name.strip(), official)

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
        cik = normalize_cik(company.cik)
        data = self.client.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", refresh=True)
        _validate_submissions(data, cik)
        section = data.get("filings", {})
        records = self._filings(section.get("recent", {}), cik)
        shards = section.get("files", [])
        for i, shard in enumerate(shards):
            name = shard.get("name", "")
            if not re.fullmatch(rf"CIK{cik}-submissions-\d+\.json", name):
                raise SecAccessError("The SEC supplied an unexpected historical-file name; retrieval stopped safely.")
            progress(f"Reading historical filing index {i + 1} of {len(shards)}…")
            historical = self.client.get_json(f"https://data.sec.gov/submissions/{name}", refresh=True)
            records.extend(self._filings(historical, cik))
        deduped = {f.accession: f for f in records}
        return sorted(deduped.values(), key=lambda f: (f.filed, f.accession))

    def _filing_document(self, filing: Filing) -> tuple[Filing, bytes | None, str]:
        if filing.primary_document:
            return filing, self.client.get_bytes(filing.source_url, ttl=30 * 86400), ""
        index = self.client.get_bytes(filing.source_url, ttl=30 * 86400)
        annual_documents, complete_submissions = _index_documents(index, filing)
        resolved = filing
        notes = []
        visited = set()
        for url in annual_documents + complete_submissions:
            if url in visited:
                continue
            visited.add(url)
            filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
            candidate = replace(filing, primary_document=filename, source_url=url)
            if resolved is filing:
                resolved = candidate
            if not filename.lower().endswith((".htm", ".html", ".txt")):
                notes.append("The listed annual document uses an unsupported format; review its source link.")
                continue
            try:
                document = self.client.get_bytes(url, ttl=30 * 86400)
            except SecAccessError as exc:
                notes.append("SEC document access failed: " + str(exc))
                continue
            if url in complete_submissions or re.search(rb"<DOCUMENT\s*>", document, re.I):
                annual_html = _annual_submission_html(document, filing.form)
                if annual_html is not None:
                    return candidate, annual_html, "Annual HTML document located inside the SEC complete submission."
                notes.append("Complete submission checked: no HTML document for this exact annual form was found. "
                             "Older plain-text statements need manual extraction.")
            elif filename.lower().endswith((".htm", ".html")) or _is_html_statement_document(document):
                return candidate, document, "Primary annual document located through the SEC filing index."
            else:
                notes.append("Annual document located, but its older plain-text format is not supported for extraction.")
        if not annual_documents and not complete_submissions:
            notes.append("Filing index checked; no annual primary document or complete submission link could be located.")
        return resolved, None, " ".join(dict.fromkeys(notes))

    def generate(self, company: Company, progress: Callable[[str], None] | None = None) -> StatementBundle:
        report = progress or (lambda _: None)
        report("Discovering annual filings and selecting the latest 20 fiscal periods…")
        filings = self.annual_filings(company, report)
        if not filings:
            raise ValueError("No supported annual SEC filings were found for this company. "
                             "Search an operating company that files annual reports, rather than a fund or ETF.")
        warnings = [
            "Statement retrieval and presentation cover up to the latest 20 fiscal periods for this SEC identifier. "
            "All discovered annual filing links and available structured raw facts remain available for source review. "
            "Older paper reports and predecessor identifiers may require manual research.",
            "Values use the latest available annual filing for each reported tag and period. "
            "Later comparative figures are not automatically proven restatements; changes are flagged for review.",
            "Verified equivalent concepts may share a historical row; original tags remain in each cell's sources. "
            "Different units and distinct reported scopes stay separate. Selected annual period starts are recorded in the sources. "
            "Blank cells mean unavailable observations, never zero. Fiscal-year and accounting changes require analyst review.",
        ]
        facts = []
        facts_warning = ""
        try:
            report("Loading SEC structured financial data…")
            payload = self.client.get_json(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company.cik.zfill(10)}.json", refresh=True)
            _validate_submissions(payload, company.cik.zfill(10))
            facts.extend(parse_company_facts(payload, filings))
        except SecAccessError as exc:
            facts_warning = f"Structured company-facts data could not be loaded: {exc}"
            warnings.append(facts_warning)
        selected_periods = set(sorted({filing.report_date for filing in filings
                                      if _valid_period(filing.report_date)}, reverse=True)[:20])
        eligible = sum(filing.report_date in selected_periods for filing in filings)
        coverage = []
        read_count = 0
        retrieval_failed = False
        for index, filing in enumerate(filings):
            if filing.report_date not in selected_periods:
                has_period = _valid_period(filing.report_date)
                coverage.append(CoverageRecord(
                    filing.accession, filing.report_date, filing.filed, filing.source_url,
                    "outside presentation window" if has_period else "unsupported",
                    "Filing document not retrieved because its fiscal period is outside the latest 20-period window. "
                    "Available SEC structured source facts are retained."
                    if has_period else "No valid annual fiscal period was reported in the filing index; "
                    "document retrieval was omitted rather than assigning a guessed period."))
                continue
            read_count += 1
            report(f"Reading annual filing {read_count} of {eligible} · {filing.report_date} · {filing.form}…")
            extracted = []
            problem = ""
            try:
                filing, document, problem = self._filing_document(filing)
                if document is None and "SEC document access failed:" in problem:
                    retrieval_failed = True
                filings[index] = filing
                if document is not None:
                    extracted = parse_filing_html(document, filing)
                    facts.extend(extracted)
            except SecAccessError as exc:
                problem = str(exc)
                retrieval_failed = True
            except ValueError:
                # Known malformed document errors become explicit coverage gaps.
                problem = "The filing's statement format could not be interpreted safely; review it manually."
            fallback = [f for f in facts if f.accession == filing.accession and f.extraction == "companyfacts"]
            found = {f.statement for f in extracted}
            fallback_found = {f.statement for f in fallback}
            issues = inspect_filing(extracted, filing.report_date) if extracted else []
            if found == set(STATEMENTS) and not issues:
                status = "extracted"
                detail = f"Primary statement observations: {len(extracted)}. Core statement checks passed."
            elif extracted:
                status = "partial"
                detail = f"Reported statements: {', '.join(sorted(found))}. Other items may use standard SEC facts."
            elif fallback:
                status = "structured fallback"
                detail = (f"Standard company-facts observations: {len(fallback)}; "
                          "company-specific detail could not be recovered from this filing.")
            else:
                status = "unsupported"
                detail = "No trustworthy annual statement values could be extracted; manual review needed."
            if problem:
                detail += " " + problem
            if issues:
                detail += " " + " ".join(issues)
            available = found | fallback_found
            if available != set(STATEMENTS):
                missing = set(STATEMENTS) - available
                detail += f" Missing statements: {', '.join(sorted(missing))}."
            coverage.append(CoverageRecord(filing.accession, filing.report_date, filing.filed,
                                           filing.source_url, status, detail))
        if retrieval_failed:
            warnings.append("One or more SEC filing documents could not be retrieved; "
                            "network or provider access prevented a complete refresh.")
        report("Preparing statement rows and source records…")
        bundle = assemble_bundle(company, filings, facts, coverage, warnings)
        bundle.warnings = list(dict.fromkeys(bundle.warnings + inspect_bundle(bundle)))
        missing = sum(c.status in {"unsupported", "partial", "structured fallback"} for c in coverage)
        if missing:
            bundle.warnings.append(f"{missing} of {len(filings)} filings have limited extraction. "
                                   "Read Sources & Coverage before using these statements in a model.")
        if not bundle.raw_facts:
            # A coverage-only workbook is useful, but make its lack of values explicit.
            bundle.warnings.append("No financial values were extracted. This workbook contains filing links and coverage only.")
        return limit_statement_history(bundle, 20)
