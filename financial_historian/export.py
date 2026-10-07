"""Build a sourced workbook without converting reported units or inventing values."""
from __future__ import annotations

from datetime import date
from io import BytesIO
import math
import re
from urllib.parse import urlsplit

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .models import Fact, STATEMENTS, StatementBundle, StatementRow


MAX_ROWS = 1_048_576
MAX_COLUMNS = 16_384
MAX_TEXT_LENGTH = 32_767
HEADER_ROW = 4
FIRST_DATA_ROW = 5

# Only an entire currency unit is scaled. USD/shares, shares, pure and other
# compound units remain in their reported unit. No currency conversion occurs.
CURRENCIES = frozenset("""
AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND
BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU
CRC CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS
GIP GMD GNF GTQ GYD HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD
JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD
MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN
NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF
SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD SSP STN SVC SYP SZL THB
TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED
VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW ZWL
""".split())

_ILLEGAL_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
_INK = "152535"
_TEAL = "007F82"
_PALE = "EFF6F8"
_MUTED = "526878"
_LINE = "DCE6EB"


def _write_text(cell, value: object) -> None:
    """Explicit string cells prevent Excel formula injection, including '='."""
    value = "" if value is None else str(value)
    if len(value) > MAX_TEXT_LENGTH:
        raise ValueError("A workbook text field exceeds Excel's 32,767-character limit.")
    if _ILLEGAL_TEXT.search(value):
        raise ValueError("A workbook text field contains characters Excel cannot store.")
    cell.value = value
    cell.data_type = "s"


def _safe_source_url(value: str) -> str | None:
    """Only official SEC HTTPS data and archive paths become clickable links."""
    if not isinstance(value, str) or re.search(r"[\s\\\x00-\x1f]", value):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.hostname not in
                {"sec.gov", "www.sec.gov", "data.sec.gov"} or
                parsed.username or parsed.password or parsed.port not in {None, 443}):
            return None
        if "%" in parsed.path or ".." in parsed.path or "//" in parsed.path:
            return None
        if not parsed.path.startswith(("/Archives/edgar/data/", "/api/xbrl/", "/submissions/")):
            return None
    except ValueError:
        return None
    return value


def _source_link(cell, source: str) -> None:
    safe = _safe_source_url(source)
    if safe:
        cell.hyperlink = safe


def _display_unit(unit: str) -> str:
    return f"{unit} million" if unit in CURRENCIES else unit


def _valid_fact(row: StatementRow, period: str, fact: Fact, statement: str) -> str | None:
    if fact.end != period:
        return f"Fact period end {fact.end} differs from column period {period}."
    if fact.unit != row.unit:
        return f"Fact unit {fact.unit} differs from row unit {row.unit}; units were not mixed."
    if fact.tag != row.tag:
        return "Fact SEC tag differs from its row tag."
    if fact.statement != statement:
        return "Fact statement differs from its worksheet."
    return None


def _fact_comment(fact: Fact, display_unit: str, rejection: str | None = None) -> Comment:
    text = "\n".join([
        f"{'Generated row identifier (no SEC tag)' if fact.tag.startswith('html:') else 'SEC tag'}: {fact.tag}", f"Reported label: {fact.label}",
        f"Source/XBRL value (unscaled): {fact.value}",
        f"Statement presentation value (unscaled): {fact.presentation_value if fact.presentation_value is not None else 'Not supplied; source value used'}",
        f"Reported unit: {fact.unit}",
        f"Display unit: {display_unit}",
        f"Annual display period start: {fact.start or 'Instant / not provided'}",
        f"Annual display period end: {fact.end}",
        f"Original instant context: {fact.source_instant or (fact.end if fact.start is None else 'Not an instant fact')}",
        f"Row role: {fact.row_role or 'Reported statement row'}",
        f"Filed: {fact.filed}", f"Form: {fact.form}",
        f"Accession: {fact.accession}", f"Source filing: {fact.source_url}",
        f"Extraction: {fact.extraction}",
        f"Selection reason: {fact.selection_reason or 'Not supplied by extraction'}",
        "A later comparative figure is not necessarily a confirmed restatement.",
        *( [f"Not displayed: {rejection}"] if rejection else [] ),
    ])
    if len(text) > MAX_TEXT_LENGTH or _ILLEGAL_TEXT.search(text):
        raise ValueError("A provenance comment exceeds Excel's text limits or contains invalid characters.")
    comment = Comment(text, "Financial Historian")
    comment.width = 460
    comment.height = 340
    return comment


def _base_sheet(workbook: Workbook, title: str, company: str, note: str, columns: int):
    sheet = workbook.create_sheet(title)
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.print_title_rows = "1:4"
    _write_text(sheet.cell(1, 1), f"{company} | {title}")
    sheet.cell(1, 1).font = Font(name="Aptos", size=18, bold=True, color="FFFFFF")
    sheet.cell(1, 1).fill = PatternFill("solid", fgColor=_INK)
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(2, columns))
    sheet.row_dimensions[1].height = 34
    _write_text(sheet.cell(2, 1), note)
    sheet.cell(2, 1).font = Font(name="Aptos", size=10, color=_MUTED)
    sheet.cell(2, 1).alignment = Alignment(wrap_text=True, vertical="top")
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(2, columns))
    sheet.row_dimensions[2].height = 30
    return sheet


def _headers(sheet, headers: list[str]) -> None:
    for col, value in enumerate(headers, 1):
        cell = sheet.cell(HEADER_ROW, col)
        _write_text(cell, value)
        cell.fill = PatternFill("solid", fgColor=_TEAL)
        cell.font = Font(name="Aptos", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    sheet.row_dimensions[HEADER_ROW].height = 30


def _style_row(sheet, row: int, columns: int) -> None:
    for col in range(1, columns + 1):
        cell = sheet.cell(row, col)
        cell.font = Font(name="Aptos", size=10, color=_INK)
        cell.alignment = Alignment(vertical="top", wrap_text=col in {1, 2})
        cell.border = Border(bottom=Side(style="hair", color=_LINE))
        if row % 2:
            cell.fill = PatternFill("solid", fgColor=_PALE)


def _check_dimensions(rows: int, columns: int, sheet_name: str) -> None:
    if rows > MAX_ROWS or columns > MAX_COLUMNS:
        raise ValueError(f"{sheet_name} exceeds Excel's {MAX_ROWS:,}-row / "
                         f"{MAX_COLUMNS:,}-column limit. No data was silently dropped.")


def build_workbook(bundle: StatementBundle) -> bytes:
    """Return an XLSX with reported statement rows and cell-level provenance.

    Periods are chronological, with no fixed history cap. Monetary units display
    in millions; source values are unscaled in Data Sheet. Inconsistent facts
    remain visible there but are withheld from the misleading statement cell.
    """
    if any(statement not in STATEMENTS for statement in bundle.statements):
        raise ValueError("An unsupported statement worksheet was supplied; no rows were dropped.")
    periods = sorted(set(bundle.periods))
    try:
        for period in periods:
            if date.fromisoformat(period).isoformat() != period:
                raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Annual period labels must be ISO dates (YYYY-MM-DD).") from None

    columns = len(periods) + 3
    for statement in STATEMENTS:
        _check_dimensions(len(bundle.statements.get(statement, [])) + HEADER_ROW, columns, statement)

    raw_facts = list(bundle.raw_facts)
    seen = set(raw_facts)
    for rows in bundle.statements.values():
        for row in rows:
            for period, fact in row.values.items():
                if period not in periods:
                    raise ValueError(f"A statement contains period {period} absent from the bundle; no data was dropped.")
                if fact not in seen:
                    raw_facts.append(fact)
                    seen.add(fact)
    for fact in raw_facts:
        if isinstance(fact.value, bool) or not isinstance(fact.value, (int, float)) or not math.isfinite(fact.value):
            raise ValueError("Financial facts must contain finite numeric values; missing values belong in blank cells.")
        if fact.presentation_value is not None and (
                isinstance(fact.presentation_value, bool) or
                not isinstance(fact.presentation_value, (int, float)) or
                not math.isfinite(fact.presentation_value)):
            raise ValueError("Statement presentation values must contain finite numeric values when supplied.")
    _check_dimensions(len(raw_facts) + HEADER_ROW, 17, "Data Sheet")
    _check_dimensions(len(bundle.filings) + len(bundle.coverage) + len(bundle.warnings) + HEADER_ROW,
                      8, "Sources & Coverage")

    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.title = "Financial Historian annual statements"
    workbook.properties.creator = "Financial Historian"
    displayed: dict[Fact, list[str]] = {}
    withheld = 0
    for statement in STATEMENTS:
        sheet = _base_sheet(workbook, statement, bundle.company.name,
                            "Monetary units: millions of the reported currency. Shares, per-share amounts and other units: unscaled. Blank = unavailable.",
                            columns)
        _write_text(sheet.cell(3, 1), "Annual period end dates; click a value for its SEC filing and inspect its comment for provenance.")
        sheet.cell(3, 1).font = Font(name="Aptos", size=10, italic=True, color=_MUTED)
        _headers(sheet, ["Narration", "Display unit", *periods, "SEC tag / row identifier"])
        sheet.freeze_panes = "C5"
        sheet.column_dimensions["A"].width = 54
        sheet.column_dimensions["B"].width = 21
        for col in range(3, columns):
            sheet.column_dimensions[get_column_letter(col)].width = 17
        sheet.column_dimensions[get_column_letter(columns)].width = 52
        rows = bundle.statements.get(statement, [])
        for row_number, row in enumerate(rows, FIRST_DATA_ROW):
            _style_row(sheet, row_number, columns)
            _write_text(sheet.cell(row_number, 1), row.label)
            _write_text(sheet.cell(row_number, 2), _display_unit(row.unit))
            _write_text(sheet.cell(row_number, columns), row.tag)
            for col, period in enumerate(periods, 3):
                fact = row.values.get(period)
                if fact is None:
                    continue
                cell = sheet.cell(row_number, col)
                rejection = _valid_fact(row, period, fact, statement)
                cell.comment = _fact_comment(fact, _display_unit(row.unit), rejection)
                if rejection:
                    withheld += 1
                    continue
                presented = fact.presentation_value if fact.presentation_value is not None else fact.value
                cell.value = presented / 1_000_000 if row.unit in CURRENCIES else presented
                cell.number_format = ("#,##0;[Red](#,##0);0" if row.unit == "shares"
                                      else "#,##0.00;[Red](#,##0.00);0.00")
                cell.alignment = Alignment(horizontal="right", vertical="top")
                _source_link(cell, fact.source_url)
                displayed.setdefault(fact, []).append(f"'{statement}'!{cell.coordinate}")
        sheet.auto_filter.ref = f"A4:{get_column_letter(columns)}{max(HEADER_ROW, len(rows) + HEADER_ROW)}"
        sheet.print_options.horizontalCentered = True

    data = _base_sheet(workbook, "Data Sheet", bundle.company.name,
                       "Raw source values and optional statement presentation values retain their reported units. Original instant contexts are separate from annual display periods. No monetary scaling or currency conversion is applied on this sheet.", 17)
    _headers(data, ["Statement", "SEC tag / row identifier", "Reported label", "Reported unit", "Source/XBRL value (unscaled)",
                    "Annual display period start", "Annual display period end", "Accession", "Filed", "Form", "Extraction", "Selection reason",
                    "Source filing", "Displayed cells", "Statement presentation value (unscaled)",
                    "Original source instant", "Row role"])
    for row_number, fact in enumerate(raw_facts, FIRST_DATA_ROW):
        _style_row(data, row_number, 17)
        values = [fact.statement, fact.tag, fact.label, fact.unit, fact.value, fact.start, fact.end,
                  fact.accession, fact.filed, fact.form, fact.extraction, fact.selection_reason,
                  fact.source_url, "; ".join(displayed.get(fact, [])), fact.presentation_value,
                  fact.source_instant, fact.row_role]
        for col, value in enumerate(values, 1):
            cell = data.cell(row_number, col)
            if col in {5, 15} and value is not None:
                cell.value = value
                cell.number_format = "#,##0.##########;[Red](#,##0.##########);0"
            elif value is not None:
                _write_text(cell, value)
        _source_link(data.cell(row_number, 13), fact.source_url)
    data.freeze_panes = "F5"
    data.auto_filter.ref = f"A4:Q{max(HEADER_ROW, len(raw_facts) + HEADER_ROW)}"
    for col in range(1, 18):
        data.column_dimensions[get_column_letter(col)].width = {2: 52, 3: 52, 6: 25, 7: 25, 12: 72, 13: 82, 14: 45, 15: 34, 16: 25}.get(col, 20)

    sources = _base_sheet(workbook, "Sources & Coverage", bundle.company.name,
                          f"{len(periods)} annual period ends | {len(raw_facts)} raw facts | "
                          f"{len(bundle.filings)} discovered filings | {len(bundle.coverage)} extraction coverage records", 8)
    _headers(sources, ["Record", "Accession", "Form", "Report end", "Filed", "Status", "Detail", "Source filing"])
    records = []
    forms = {filing.accession: filing.form for filing in bundle.filings}
    for filing in bundle.filings:
        records.append(["Filing", filing.accession, filing.form, filing.report_date, filing.filed,
                        "Discovered", "Metadata only; see extraction coverage records for availability.", filing.source_url])
    for coverage in bundle.coverage:
        records.append(["Coverage", coverage.accession, forms.get(coverage.accession, ""), coverage.report_date,
                        coverage.filed, coverage.status, coverage.detail, coverage.source_url])
    for warning in bundle.warnings:
        records.append(["Warning", "", "", "", "", "Notice", warning, ""])
    for row_number, record in enumerate(records, FIRST_DATA_ROW):
        _style_row(sources, row_number, 8)
        for col, value in enumerate(record, 1):
            _write_text(sources.cell(row_number, col), value)
        _source_link(sources.cell(row_number, 8), record[7])
        sources.cell(row_number, 7).alignment = Alignment(wrap_text=True, vertical="top")
    sources.freeze_panes = "C5"
    sources.auto_filter.ref = f"A4:H{max(HEADER_ROW, len(records) + HEADER_ROW)}"
    for col, width in enumerate([15, 26, 12, 16, 16, 24, 88, 85], 1):
        sources.column_dimensions[get_column_letter(col)].width = width

    readme = _base_sheet(workbook, "Read Me", bundle.company.name,
                         "Reported annual financial history for research. Review source filings before using the figures in a projection model.", 2)
    _headers(readme, ["Topic", "Explanation"])
    notes = [
        ("Company", bundle.company.name), ("Ticker", bundle.company.ticker), ("SEC CIK", bundle.company.cik),
        ("Generated (UTC)", bundle.generated_at),
        ("Annual history", "All retrievable annual periods are included in chronological order. There is no 10-year or 50-year cap. Available data does not prove complete lifetime coverage."),
        ("Presentation", "Annual columns and statement tabs follow the supplied reference workbook's broad layout. No Indian-company data, ratios, forecast columns or financial modeling are carried over."),
        ("Units", "Pure currency amounts display in millions of their own reported currency. Shares, currency per share, ratios and all other units are unscaled. The Display unit column is authoritative. No currency conversion occurs."),
        ("Raw values", "Data Sheet stores every supplied raw fact and every selected statement fact, unscaled. Displayed cells identifies the statement cell using each selected fact."),
        ("Presentation signs", "Where the filing's visible statement sign is available, statement tabs use that presentation value. For example, an XBRL payments concept can be positive while its cash-flow line is shown negative. Data Sheet keeps the underlying Source/XBRL value and optional Statement presentation value separately, both unscaled."),
        ("Cash-flow reconciliation", "Beginning and ending cash can use the same original SEC concept with different instant dates. They remain separate reported rows, identified by cash_begin/cash_end row roles. Annual display period columns identify the verified year being reconciled; Original source instant preserves each actual XBRL context date. These display periods do not turn cash balances into duration facts."),
        ("Missing values", "Blank cells mean unavailable or withheld, never an assumed zero. A reported zero remains numerical zero. A comment explains any fact withheld because its period, unit, tag or statement differs from its row."),
        ("Latest reported history", "Selection aims to use the latest available annual filed representation for a comparable historical period. A later comparative figure is not necessarily a confirmed restatement. Read each cell's selection reason and filing date."),
        ("SEC companyfacts limits", "The SEC companyfacts API contains standardized entity-level XBRL facts, generally from the modern structured reporting era. It is not a complete statement presentation, omits company-specific custom tags and dimensions, and does not establish 50+ years of coverage."),
        ("Older filings", "Older or unsupported filings may have no extractable numerical facts. Sources & Coverage records discovered filings, supported extraction, unsupported formats and reported gaps. Missing years are not estimated."),
        ("Untagged row identifiers", "Identifiers beginning html: are locally generated from an untagged statement label. They are not SEC XBRL tags. Consult the source filing and extraction notes."),
        ("Comparability", "Company labels and SEC tags are preserved where supplied. Tags may change or overlap across years; rows are not automatically combined. Different units remain separate. Fiscal periods may have different ends or lengths; inspect start and end dates."),
        ("Analyst adjustments", "Figures remain as reported in the selected source. No normalization of one-time expenses, valuations, growth forecasts or analyst adjustments is performed."),
        ("Provenance", "Every displayed numeric statement value has a comment with SEC tag, raw unit/value, accession, filed date, period dates, extraction and selection reason. Valid SEC source URLs are clickable."),
        ("Link policy", "Only HTTPS links on sec.gov, www.sec.gov or data.sec.gov using SEC archive/XBRL/submissions paths become hyperlinks. Other source text remains literal and is not executable."),
        ("Excel text safety", "All company names, labels, tags, warnings, metadata and source text are written as literal strings, including text beginning with =, +, - or @. The workbook contains no formulas."),
        ("Withheld inconsistent cells", str(withheld)),
    ]
    for row_number, (topic, explanation) in enumerate(notes, FIRST_DATA_ROW):
        _style_row(readme, row_number, 2)
        _write_text(readme.cell(row_number, 1), topic)
        _write_text(readme.cell(row_number, 2), explanation)
        readme.cell(row_number, 2).alignment = Alignment(wrap_text=True, vertical="top")
        readme.row_dimensions[row_number].height = 48
    readme.column_dimensions["A"].width = 29
    readme.column_dimensions["B"].width = 120
    readme.freeze_panes = "B5"

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
