"""Shared records. Values keep their reported unit; missing values stay missing."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

STATEMENTS = ("Profit & Loss", "Balance Sheet", "Cash Flow")


@dataclass(frozen=True)
class Company:
    cik: str
    name: str
    ticker: str = ""
    sic: str = ""


@dataclass(frozen=True)
class Filing:
    accession: str
    form: str
    filed: str
    report_date: str
    primary_document: str
    source_url: str


@dataclass(frozen=True)
class Fact:
    tag: str
    label: str
    unit: str
    value: float
    start: str | None
    end: str
    accession: str
    filed: str
    form: str
    source_url: str
    statement: str
    extraction: str = "companyfacts"
    # Explicit provenance; a later comparative is not necessarily a restatement.
    selection_reason: str = ""
    # XBRL payments may be positive by concept while printed as cash outflows.
    # Keep the tagged value above and the statement's visible sign separately.
    presentation_value: float | None = None
    # Cash-flow reconciliation instants retain their actual context date while
    # occupying the verified full-year presentation column in start/end.
    row_role: str = ""
    source_instant: str | None = None
    # Reported section disambiguates repeated labels such as "Other".
    section: str = ""
    context_id: str = ""
    dimensions: tuple[tuple[str, str], ...] = ()
    decimals: str = ""


@dataclass
class StatementRow:
    tag: str
    label: str
    unit: str
    values: dict[str, Fact] = field(default_factory=dict)
    # Only verified equivalent source concepts may share a historical row.
    accepted_tags: set[str] = field(default_factory=set)
    section: str = ""
    is_total: bool = False


@dataclass(frozen=True)
class CoverageRecord:
    accession: str
    report_date: str
    filed: str
    source_url: str
    status: str
    detail: str


@dataclass
class StatementBundle:
    company: Company
    periods: list[str] = field(default_factory=list)
    statements: dict[str, list[StatementRow]] = field(default_factory=lambda: {s: [] for s in STATEMENTS})
    raw_facts: list[Fact] = field(default_factory=list)
    filings: list[Filing] = field(default_factory=list)
    coverage: list[CoverageRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    disclosures: list[Fact] = field(default_factory=list)
