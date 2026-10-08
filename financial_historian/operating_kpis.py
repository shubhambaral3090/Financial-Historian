"""Reviewed exact issuer/tag mappings, never inferred KPIs from loose labels."""
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class KpiMapping:
    cik: str
    tag: str
    label: str
    unit: str
    period_type: str
    definition: str
    source_url: str
    verified_on: str


def load_kpi_mappings(cik: str, path: Path | None = None) -> tuple[KpiMapping, ...]:
    """Invalid registry fails closed; callers surface a nonfatal coverage note."""
    from .export import _safe_source_url
    path = path or Path(__file__).resolve().parent.parent / "config" / "operating_kpis.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("mappings"), list):
        raise ValueError("Invalid operating KPI registry schema")
    result, seen = [], set()
    for item in payload["mappings"]:
        if not isinstance(item, dict) or set(item) != set(KpiMapping.__dataclass_fields__):
            raise ValueError("KPI mapping fields are incomplete")
        if not all(isinstance(value, str) and value.strip() and len(value) <= 2000 for value in item.values()):
            raise ValueError("Invalid KPI mapping text")
        row = KpiMapping(**item)
        if not re.fullmatch(r"\d{10}", row.cik) or row.cik == "0000000000" or not re.fullmatch(r"[A-Za-z_][\w.-]*:[A-Za-z_][\w.-]*", row.tag):
            raise ValueError("Invalid issuer or exact tag")
        if row.period_type not in {"instant", "annual"} or not _safe_source_url(row.source_url):
            raise ValueError("KPI needs an explicit period type and SEC evidence URL")
        # Do not accept a link to a different issuer as mapping evidence.
        if not re.search(r"/Archives/edgar/data/0*" + str(int(row.cik)) + r"/", row.source_url):
            raise ValueError("KPI evidence must reference the mapped issuer")
        date.fromisoformat(row.verified_on)
        identity = (row.cik, row.tag, row.unit, row.period_type)
        if identity in seen:
            raise ValueError("Conflicting or duplicate KPI mappings")
        seen.add(identity)
        if row.cik == cik.zfill(10):
            result.append(row)
    return tuple(result)
