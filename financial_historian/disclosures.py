"""Bounded, explicitly scoped annual note facts; never merged into face statements."""
from lxml import html, etree
import math

from .models import Fact, Filing
from .extract import (_local, _text, _attr, _units, _number, _fact_text,
                      _row_label, _annual_duration, _valid_end, _date, ANNUAL_FORMS)

# Exact concepts only; long-term debt is not total company debt.
NOTE_TAGS = {
    "DebtCurrent": "Debt & Liquidity", "DebtNoncurrent": "Debt & Liquidity",
    "DebtAndCapitalLeaseObligations": "Debt & Liquidity",
    "DebtInstrumentCarryingAmount": "Debt & Liquidity",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths": "Debt & Liquidity",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo": "Debt & Liquidity",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree": "Debt & Liquidity",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour": "Debt & Liquidity",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive": "Debt & Liquidity",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive": "Debt & Liquidity",
    "PropertyPlantAndEquipmentGross": "Capital & PP&E",
    "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment": "Capital & PP&E",
    "Depreciation": "Capital & PP&E", "DepreciationDepletionAndAmortization": "Capital & PP&E",
    "CommonStockholdersEquity": "Equity & Shares",
    "NetIncomeLossAvailableToCommonStockholdersBasic": "Equity & Shares",
    "InterestExpense": "Debt & Liquidity", "InterestExpenseNonOperating": "Debt & Liquidity",
    "InterestExpenseNonoperating": "Debt & Liquidity",
    "ProfitLoss": "EBITDA & Capital",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": "EBITDA & Capital",
    "IncomeTaxExpenseBenefit": "EBITDA & Capital",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": "EBITDA & Capital",
    "PaymentsOfDividendsCommonStock": "Equity & Shares",
    "CommonStockDividendsPerShareDeclared": "Equity & Shares",
    "WeightedAverageNumberOfDilutedSharesOutstanding": "Equity & Shares",
    "EarningsPerShareDiluted": "Equity & Shares",
    "EarningsPerShareBasic": "Equity & Shares",
}


def parse_company_disclosures(payload: dict, filings: list[Filing]) -> list[Fact]:
    """Curated entity-wide note concepts from the SEC API, without invented context IDs."""
    filing_map = {f.accession:f for f in filings}
    ends = {f.report_date for f in filings}
    output = []
    for local,group in NOTE_TAGS.items():
        concept = payload.get("facts",{}).get("us-gaap",{}).get(local,{})
        for unit,observations in concept.get("units",{}).items():
            for obs in observations:
                filing = filing_map.get(obs.get("accn"))
                if not filing or obs.get("form") not in ANNUAL_FORMS:
                    continue
                start,end = obs.get("start"),obs.get("end","")
                if not _valid_end(end,filing) or not _date(obs.get("filed")):
                    continue
                if start and not _annual_duration(start,end) or not start and end not in ends:
                    continue
                value = obs.get("val")
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                    continue
                output.append(Fact("us-gaap:"+local,concept.get("label") or local,unit,float(value),start,end,
                                   filing.accession,obs["filed"],obs["form"],filing.source_url,"Disclosure",
                                   "companyfacts-note",section=group,
                                   selection_reason="Curated SEC companyfacts note concept; context ID and source precision are not supplied by this API."))
    return output


def parse_disclosures(content: bytes, filing: Filing, kpi_mappings=()) -> list[Fact]:
    if filing.form not in ANNUAL_FORMS:
        return []
    try:
        root = html.fromstring(content)
    except (ValueError, etree.ParserError):
        return []
    contexts = {}
    for node in root.iter():
        if not isinstance(node.tag, str) or _local(node.tag) != "context":
            continue
        dates, dimensions = {}, []
        for child in node.iter():
            if not isinstance(child.tag, str):
                continue
            name = _local(child.tag)
            if name in {"startdate", "enddate", "instant"}:
                dates[name] = _text(child)
            if name in {"explicitmember", "typedmember"}:
                dimensions.append((_attr(child, "dimension"), _text(child)))
        end = dates.get("enddate") or dates.get("instant")
        if end and _date(end):
            contexts[_attr(node, "id")] = (dates.get("startdate"), end, tuple(sorted(dimensions)))
    annual = {end for start, end, _ in contexts.values() if _annual_duration(start, end)} | {filing.report_date}
    units, result, seen = _units(root), [], set()
    for node in root.iter():
        if not isinstance(node.tag, str) or _local(node.tag) != "nonfraction":
            continue
        tag = _attr(node, "name")
        local = tag.rsplit(":", 1)[-1]
        context_id = _attr(node, "contextref")
        context = contexts.get(context_id)
        if not context or _attr(node, "nil").lower() in {"true", "1"}:
            continue
        start, end, dimensions = context
        segment = dimensions and any("segment" in axis.lower() or "geograph" in axis.lower()
                                     or "product" in axis.lower() for axis, member in dimensions)
        group = "Revenue & Segments" if segment else NOTE_TAGS.get(local) if tag.startswith("us-gaap:") else None
        kpi = next((entry for entry in kpi_mappings if entry.tag == tag
                    and entry.period_type == ("annual" if start else "instant")
                    and entry.unit == units.get(_attr(node, "unitref"))), None)
        if kpi:
            group = "Operating KPIs"
        if not group or not _valid_end(end, filing):
            continue
        if start and not _annual_duration(start, end) or not start and end not in annual:
            continue
        unit = units.get(_attr(node, "unitref"))
        value = _number(_fact_text(node), transform=_attr(node, "format"), sign=_attr(node, "sign"), scale=_attr(node, "scale", "0"))
        if not unit or value is None:
            continue
        identity = (tag, unit, start, end, dimensions, value, context_id, _attr(node, "decimals"))
        if identity in seen:
            continue
        seen.add(identity)
        result.append(Fact(tag, _row_label(node, tag), unit, value, start, end,
                           filing.accession, filing.filed, filing.form, filing.source_url,
                           "Disclosure", "inline-note", section=group,
                           row_role="kpi:" + tag if kpi else "",
                           context_id=context_id, dimensions=dimensions, decimals=_attr(node, "decimals"),
                           selection_reason=(f"Reviewed KPI: {kpi.label}. Definition: {kpi.definition}. Mapping evidence: {kpi.source_url}; reviewed {kpi.verified_on}. " if kpi else "")
                           + "Annual disclosure; member scopes are separate and not assumed additive. "
                           + ("Contractual maturity bucket at the reporting date, not realized cash flow." if "Maturit" in tag else "")))
    return result
