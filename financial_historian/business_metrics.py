"""Annual member-level metrics without inventing segment continuity or additivity."""
from decimal import Decimal

REVENUE_TAGS = {
    "us-gaap:Revenues": "revenue",
    "us-gaap:SalesRevenueNet": "net_sales",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": "contract_revenue",
    "ifrs-full:Revenue": "revenue",
}


def build_business_metrics(engine, schedules):
    from .analysis import AnalysisRow, combine, currency, definition, missing, quantum
    from .extended_metrics import same_filing_prior
    output = []
    for group in ("Revenue & Segments", "Operating KPIs"):
        for index, row in enumerate(schedules[group]):
            facts = [item.fact for item in row.cells.values() if item.fact]
            if not facts:
                continue
            sample = facts[0]
            is_kpi = group == "Operating KPIs" and sample.row_role.startswith("kpi:")
            is_revenue = bool(sample.dimensions and sample.start and sample.tag in REVENUE_TAGS and currency(sample.unit))
            if not is_kpi and not is_revenue:
                continue
            modes = ("growth",) if is_kpi else ("growth", "mix")
            for mode in modes:
                label = row.definition.label + (" — annual growth" if mode == "growth" else " — revenue share")
                d = definition(f"business:{group}:{index}:{mode}", label, "Business drivers",
                               "Current / same-filing prior − 1" if mode == "growth" else "Member revenue / same-concept consolidated revenue",
                               "%", row.definition.purpose if is_kpi else "Reported business-driver growth or contribution to the matching revenue total.",
                               "Same exact tag, member and unit; no inferred unique users or recurring revenue." if is_kpi else "Members may overlap and need not sum to 100%. Same-filing comparatives do not prove unchanged business composition; acquisitions remain included.")
                cells = {}
                for p in engine.periods:
                    current = row.cells[p]
                    if mode == "growth":
                        previous = engine.prior(p)
                        prior = same_filing_prior(engine, current, previous) if previous else missing(label, p, "A consecutive annual comparison is required.")
                        if current.value is not None and current.value < 0:
                            cells[p] = missing(label, p, "Negative revenue or KPI count is not a supported growth numerator.", "%")
                        else:
                            cells[p] = combine(label, p, "%", "{0}/{1}-1", (current, prior), lambda x,y:x/y-1, prior)
                    else:
                        denominator = engine.get(REVENUE_TAGS[sample.tag], p)
                        if current.value is not None and denominator.value is not None and current.unit != denominator.unit:
                            cells[p] = missing(label, p, "Member and consolidated revenue units do not match.", "%")
                            continue
                        result = combine(label, p, "%", "{0}/{1}", (current, denominator), lambda x,y:x/y, denominator)
                        if result.value is not None:
                            tolerance = sum((quantum(f)/2 for f in result.sources), Decimal("0.000001"))
                            if current.value < 0 or current.value - denominator.value > tolerance:
                                result = missing(label, p, "Member revenue is negative or exceeds the consolidated total; eliminations or scope differences require review.", "%")
                        cells[p] = result
                output.append(AnalysisRow(d, cells))
    return output
