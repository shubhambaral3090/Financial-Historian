"""One validated financial presentation for the browser and Excel workbook.

This layer never repairs, relabels, combines or changes a source observation.
Inconsistent cell assignments are withheld from the displayed statement, while
their untouched facts remain in the audit data with an explicit explanation.
"""
from __future__ import annotations

from dataclasses import replace

from .models import Fact, StatementBundle, StatementRow


def fact_rejection(row: StatementRow, period: str, fact: Fact, statement: str) -> str | None:
    """Return the shared display/export rejection reason, or accept the fact."""
    if fact.end != period:
        return f"Fact period end {fact.end} differs from column period {period}."
    if fact.unit != row.unit:
        return f"Fact unit {fact.unit} differs from row unit {row.unit}; units were not mixed."
    if fact.tag != row.tag and fact.tag not in row.accepted_tags:
        return "Fact SEC tag differs from its row tag."
    if fact.statement != statement:
        return "Fact statement differs from its worksheet."
    return None


def prepare_presentation(bundle: StatementBundle) -> StatementBundle:
    """Copy and validate selected cells before either consumer can display them.

    Original raw records are retained, including any selected observation that
    was absent from raw_facts. Blank periods, labels, scopes, source signs and
    units are not changed. Reapplying the function does not duplicate notes.
    """
    raw_facts = list(bundle.raw_facts)
    seen = set(raw_facts)
    warnings = list(bundle.warnings)
    statements: dict[str, list[StatementRow]] = {}
    for statement, rows in bundle.statements.items():
        prepared = []
        for row in rows:
            values = {}
            for period, fact in row.values.items():
                if fact not in seen:
                    raw_facts.append(fact)
                    seen.add(fact)
                rejection = fact_rejection(row, period, fact, statement)
                if rejection is None:
                    values[period] = fact
                else:
                    warnings.append(
                        f"Withheld from statement presentation: {statement}, {row.label} "
                        f"[{row.tag}; {row.unit}], {period}. {rejection} "
                        "The original observation remains in Source Data; the displayed cell is blank."
                    )
            prepared.append(replace(row, values=values, accepted_tags=set(row.accepted_tags)))
        statements[statement] = prepared
    return replace(bundle, statements=statements, raw_facts=raw_facts,
                   periods=list(bundle.periods), filings=list(bundle.filings),
                   coverage=list(bundle.coverage), warnings=list(dict.fromkeys(warnings)))
