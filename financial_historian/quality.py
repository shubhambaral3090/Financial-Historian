"""Check statement anchors and reported reconciliations without inventing values.

Passing these checks is not a financial audit or proof of complete extraction.
They catch missing core rows and arithmetic disagreements in the selected data.
"""
from collections import defaultdict
import math

from .models import Fact, STATEMENTS, StatementBundle
from .normalization import concept_key


def _values(facts: list[Fact]) -> dict[str, float]:
    grouped = defaultdict(set)
    for fact in facts:
        value = fact.presentation_value if fact.presentation_value is not None else fact.value
        if math.isfinite(value):
            grouped[concept_key(fact)].add(value)
    # Contradictory duplicate observations cannot establish a reconciliation.
    return {key: next(iter(values)) for key, values in grouped.items() if len(values) == 1}


def _arithmetic_issues(facts: list[Fact], *, combine_sources: bool = False) -> list[str]:
    groups = defaultdict(list)
    for fact in facts:
        # Keep currencies and original filing presentations separate. Mixing
        # later reclassifications could create a spurious arithmetic failure.
        groups[(fact.statement, fact.unit, "selected" if combine_sources else fact.accession, fact.start)].append(fact)
    issues = []
    for (statement, unit, _, _), observations in groups.items():
        values = _values(observations)

        def compare(left: float, right: float, label: str) -> None:
            # Published tables can round each line independently. Permit 0.001%
            # of the compared amounts, or one unit for small/unscaled values.
            tolerance = max(1.0, max(abs(left), abs(right)) * 0.00001)
            if abs(left - right) > tolerance:
                issues.append(f"{label} does not reconcile ({unit}; difference {left - right:,.6g}).")

        if statement == STATEMENTS[1]:
            if {"assets", "liabilities_and_equity"} <= values.keys():
                compare(values["assets"], values["liabilities_and_equity"], "Assets versus liabilities and equity")
            equity = "equity_including_nci" if "equity_including_nci" in values else "equity"
            if {"assets", "liabilities", equity} <= values.keys():
                # Parent-only equity cannot be compared with consolidated assets
                # if noncontrolling interests are present as a separate row.
                has_nci = any("Noncontrolling" in f.tag or "MinorityInterest" in f.tag for f in observations)
                if equity == "equity_including_nci" or not has_nci:
                    compare(values["assets"], values["liabilities"] + values[equity], "Assets versus liabilities plus equity")
        if statement == STATEMENTS[2]:
            for prefix in ("", "restricted_"):
                begin, end, change = prefix + "cash_begin", prefix + "cash_end", prefix + "cash_change"
                if {begin, end, change} <= values.keys():
                    compare(values[end] - values[begin], values[change], "Beginning/ending cash versus reported cash change")
            # A disclosed FX amount is needed: absence of a retrieved FX row
            # cannot be treated as proof that the effect was zero.
            fx = [f for f in observations if f.tag.rsplit(":", 1)[-1] in {
                "EffectOfExchangeRateOnCashAndCashEquivalents",
                "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                "EffectOfExchangeRateChangesOnCashAndCashEquivalents",
            }]
            if {"cfo", "cfi", "cff"} <= values.keys() and len(fx) == 1:
                change_key = "restricted_cash_change" if "RestrictedCash" in fx[0].tag else "cash_change"
                if change_key in values:
                    amount = fx[0].presentation_value if fx[0].presentation_value is not None else fx[0].value
                    compare(values["cfo"] + values["cfi"] + values["cff"] + amount,
                            values[change_key], "Operating/investing/financing cash flows plus exchange effects")
    return list(dict.fromkeys(issues))


def inspect_filing(facts: list[Fact], report_date: str) -> list[str]:
    """Return explicit limitations for the filing's own annual report period."""
    selected = [fact for fact in facts if fact.end == report_date]
    keys = {concept_key(fact) for fact in selected}
    missing = []
    for key, label in (("revenue", "revenue"), ("net_income", "net income"),
                       ("assets", "total assets"), ("cfo", "operating cash flow"),
                       ("cfi", "investing cash flow"), ("cff", "financing cash flow")):
        if key not in keys:
            missing.append(label)
    if "liabilities_and_equity" not in keys and not (
        "liabilities" in keys and {"equity", "equity_including_nci"} & keys
    ):
        missing.append("liabilities and equity totals")
    issues = ["Core rows not verified for the report period: " + ", ".join(missing) + "."] if missing else []
    return issues + _arithmetic_issues(selected)


def inspect_bundle(bundle: StatementBundle) -> list[str]:
    """Flag gaps in the actual selected annual sheets, including raw-data recovery."""
    by_period = defaultdict(list)
    for rows in bundle.statements.values():
        for row in rows:
            for period, fact in row.values.items():
                by_period[period].append(fact)
    issues = []
    for period in sorted(by_period):
        for issue in inspect_filing(by_period[period], period):
            issues.append(f"{period}: {issue}")
        if len({fact.accession for fact in by_period[period]}) > 1:
            for issue in _arithmetic_issues(by_period[period], combine_sources=True):
                issues.append(f"{period}: Selected values from different filings: {issue}")
    return list(dict.fromkeys(issues))
