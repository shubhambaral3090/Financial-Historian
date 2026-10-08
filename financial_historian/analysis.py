"""Descriptive historical calculations with an inspectable dependency graph.

No forecast parameters, imputation, synthetic balancing items or inferred taxes.
Decimal arithmetic retains input precision until browser/XLSX presentation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import math
import re

from .models import Fact, StatementBundle, StatementRow, STATEMENTS
from .normalization import concept_key
from .presentation import prepare_presentation

P, B, C = STATEMENTS


@dataclass(frozen=True)
class Datum:
    label: str
    period: str
    unit: str
    value: Decimal | None = None
    formula: str = ""
    inputs: tuple[Datum, ...] = ()
    fact: Fact | None = None
    reason: str = ""

    @property
    def sources(self) -> tuple[Fact, ...]:
        if self.fact:
            return (self.fact,)
        return tuple(dict.fromkeys(f for item in self.inputs for f in item.sources))


@dataclass(frozen=True)
class Definition:
    key: str
    label: str
    group: str
    formula: str
    unit: str
    purpose: str
    limitation: str
    industrial: bool = False
    reference: str = "Historical ratio convention; product definition."


@dataclass
class AnalysisRow:
    definition: Definition
    cells: dict[str, Datum] = field(default_factory=dict)


@dataclass(frozen=True)
class Check:
    period: str
    label: str
    status: str
    difference: Decimal | None
    tolerance: Decimal | None
    reason: str


@dataclass
class Analysis:
    periods: list[str]
    rows: list[AnalysisRow]
    schedules: dict[str, list[AnalysisRow]]
    common_size: list[AnalysisRow]
    checks: list[Check]
    notes: list[str]


def definition(key, label, group, formula, unit, purpose, limitation, industrial=False, reference="Historical ratio convention; product definition."):
    return Definition(key, label, group, formula, unit, purpose, limitation, industrial, reference)


DEFINITIONS = [
    definition("revenue_growth", "Revenue growth", "Growth", "Revenue / prior equivalent revenue − 1", "%", "Change in the selected revenue basis over one fiscal year.", "An acquisition or change in revenue definition can prevent like-for-like comparison."),
    definition("revenue_cagr", "Revenue CAGR — 3 annual intervals", "Growth", "(Revenue / revenue 3 annual intervals earlier)^(1/3) − 1", "%", "Annualized historical change between positive endpoints.", "Requires four consecutive observations of equivalent scope; smooths intervening changes."),
    definition("gross_margin", "Gross margin", "Profitability", "Gross profit / matching sales", "%", "Share of sales remaining after reported cost of sales.", "Only calculated when the sales/cost/gross-profit relationship reconciles; industries differ.", True),
    definition("operating_margin", "Operating margin", "Profitability", "Operating income / selected revenue", "%", "Reported operating income per unit of revenue.", "Reported classifications and unusual charges affect comparison.", True),
    definition("net_margin", "Parent net margin", "Profitability", "Parent net income / selected revenue", "%", "Parent earnings relative to revenue.", "Parent earnings and consolidated revenue have different ownership scope; this is labelled explicitly."),
    definition("sga_intensity", "SG&A / revenue", "Profitability", "SG&A / selected revenue", "%", "Reported selling, general and administrative expense relative to revenue.", "Some issuers include costs that others report separately.", True),
    definition("rd_intensity", "R&D / revenue", "Profitability", "R&D / selected revenue", "%", "Reported research and development expense relative to revenue.", "Capitalized development costs are not inferred.", True),
    definition("capex_intensity", "PP&E purchases / revenue", "Capital investment", "ABS(PP&E purchases) / selected revenue", "%", "Cash investment in PP&E relative to revenue.", "Acquisitions, noncash additions and other productive assets are not included.", True),
    definition("roa", "Return on assets — consolidated", "Returns", "Consolidated net income / average total assets", "%", "Consolidated earnings relative to assets employed.", "Average uses two year-end balances; acquisitions can distort the comparison."),
    definition("roe", "Return on common equity", "Returns", "Common-shareholder income / average common equity", "%", "Common-shareholder earnings relative to common equity.", "Requires explicit common income and equity; parent equity is not assumed to exclude preferred equity."),
    definition("current_ratio", "Current ratio", "Liquidity", "Current assets / current liabilities", "x", "Relationship between reported short-term assets and obligations.", "It does not measure the timing or realizability of individual assets.", True),
    definition("quick_ratio", "Quick ratio — strict components", "Liquidity", "(Cash + short-term investments + net trade receivables) / current liabilities", "x", "Specified liquid asset components relative to current liabilities.", "Every component must be disclosed; absent investments are not treated as zero.", True),
    definition("net_debt", "Reported debt incl. finance leases less cash", "Debt", "Reported total debt including finance leases − cash equivalents", "currency", "Specified borrowing measure after deducting cash equivalents.", "Requires a reported total; restricted cash and investments are not deducted.", True),
    definition("debt_assets", "Reported debt incl. finance leases / assets", "Debt", "Reported total debt including finance leases / total assets", "%", "Reported borrowing measure relative to assets.", "Do not equate this definition to covenant debt; overlapping borrowing rows are not summed.", True),
    definition("interest_coverage", "Operating income / interest expense", "Debt", "Operating income / separately reported interest expense", "x", "Historical operating income relative to interest expense.", "Not EBITDA or covenant coverage; net finance expense is not substituted.", True),
    definition("receivable_days", "Receivable days — sales proxy", "Working capital", "Average net trade receivables / sales × fiscal days", "days", "Trade receivables expressed in equivalent days of sales.", "Uses all sales as a proxy for credit sales; two-point average balances.", True),
    definition("inventory_days", "Inventory days", "Working capital", "Average inventory / cost of sales × fiscal days", "days", "Inventory relative to annual cost of sales.", "Inventory accounting policies and seasonal year-end balances affect comparison.", True),
    definition("payable_days", "Payable days — cost-of-sales proxy", "Working capital", "Average trade payables / cost of sales × fiscal days", "days", "Trade payables expressed in equivalent days of cost of sales.", "Purchases are unavailable: cost of sales is an explicitly labelled proxy.", True),
    definition("cash_cycle", "Cash conversion cycle — proxy", "Working capital", "Receivable days + inventory days − payable days", "days", "Combines the three historical working-capital day measures.", "Inherits all sales, purchases, seasonality and average-balance limitations.", True),
    definition("ocf_margin", "Operating cash flow / revenue", "Cash generation", "Total OCF / selected revenue", "%", "Historical operating cash flow per unit of revenue.", "Tax, interest and working-capital timing affect the result.", True),
    definition("cash_conversion", "Operating cash flow / earnings", "Cash generation", "Total OCF / consolidated net income", "x", "Cash generation relative to positive consolidated earnings.", "Both measures must have total-operations scope. Unavailable for nonpositive earnings."),
    definition("ocf_capex", "Operating cash flow less PP&E purchases", "Cash generation", "Total OCF − ABS(PP&E purchases)", "currency", "Historical operating cash remaining after specified cash PP&E purchases.", "Not standardized free cash flow; acquisitions and noncash investment are excluded."),
    definition("earnings_cash", "Earnings less operating cash flow", "Earnings and cash", "Consolidated net income − total OCF", "currency", "Historical difference between earnings and operating cash flow.", "Not the original Sloan (1996) accrual construction; no earnings-quality verdict.", reference="Sloan (1996), pp. 293–294; explicitly different product adaptation."),
    definition("accrual_assets", "Earnings–cash difference / average assets", "Earnings and cash", "(Consolidated net income − total OCF) / average assets", "%", "Scales the historical earnings–cash difference by assets.", "Differences can arise from ordinary operations; not a fraud signal or Sloan replication.", reference="Sloan (1996), pp. 293–294; product adaptation."),
    definition("asset_turnover", "Asset turnover — total assets", "Return bridge", "Selected revenue / average total assets", "x", "Revenue relative to total assets employed.", "Uses total assets, not net operating assets.", True),
    definition("operating_return", "Operating return on total assets", "Return bridge", "Operating income / average total assets", "%", "Pretax operating return on a total-assets base.", "Not after-tax RNOA or ROIC; financing assets remain in the denominator.", True),
    definition("return_change", "Change in operating return", "Return bridge", "Current operating return − prior operating return", "pp", "Historical change in the defined return measure.", "Percentage-point change, not percentage growth.", True),
    definition("margin_contribution", "Margin-change contribution", "Return bridge", "Prior turnover × (current margin − prior margin)", "pp", "Arithmetic portion associated with the margin change.", "A mathematical attribution, not evidence of economic causation.", True, "Fairfield & Yohn (2001), p. 375; total-assets adaptation."),
    definition("turnover_contribution", "Turnover-change contribution", "Return bridge", "Prior margin × (current turnover − prior turnover)", "pp", "Arithmetic portion associated with the turnover change.", "A mathematical attribution, not evidence of economic causation.", True, "Fairfield & Yohn (2001), p. 375; total-assets adaptation."),
    definition("interaction", "Margin/turnover interaction", "Return bridge", "(Current margin − prior margin) × (current turnover − prior turnover)", "pp", "Interaction needed to reconcile the change exactly.", "Includes simultaneous changes; does not establish a cause.", True, "Fairfield & Yohn (2001), p. 375; total-assets adaptation."),
]

# Exact mappings; no fuzzy labels or company-name guessing.
EXTRA_TAGS = {
    "net_income_total": (P, {"us-gaap:ProfitLoss"}),
    "common_income": (P, {"us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic"}),
    "common_equity": (B, {"us-gaap:CommonStockholdersEquity"}),
    "interest": (P, {"us-gaap:InterestExpense", "us-gaap:InterestExpenseNonOperating"}),
    "debt_total": (B, {"us-gaap:DebtAndCapitalLeaseObligations"}),
    "ppe_gross": (B, {"us-gaap:PropertyPlantAndEquipmentGross"}),
}

SCHEDULE_KEYS = {
    "Revenue & Segments": {"revenue", "net_sales", "contract_revenue", "gross_profit", "operating_income"},
    "Working Capital": {"receivables", "nontrade_receivables", "inventory", "payables", "other_current_assets", "other_current_liabilities", "current_assets", "current_liabilities", "deferred_revenue_current"},
    "Debt & Liquidity": {"cash", "marketable_current", "short_term_investments", "marketable_noncurrent", "debt_current", "debt_noncurrent", "commercial_paper", "debt_total", "interest", "interest_paid", "debt_issuance", "debt_repayment"},
    "Capital & PP&E": {"ppe", "ppe_gross", "capex", "depreciation"},
    "Earnings & Cash": {"net_income", "net_income_total", "cfo", "cfo_continuing", "depreciation", "stock_compensation", "receivables_change", "inventory_change", "payables_change", "capex"},
    "Equity & Shares": {"equity", "equity_including_nci", "common_equity", "common_income", "shares_basic", "shares_diluted", "eps_basic", "eps_diluted", "dividends", "repurchases", "stock_compensation", "retained_earnings", "treasury_stock"},
}


def semantic_key(fact: Fact) -> str:
    for key, (statement, tags) in EXTRA_TAGS.items():
        if fact.tag in tags and fact.statement in {statement, "Disclosure"}:
            return key
    key = concept_key(fact)
    return {"accounts_payable":"payables", "share_compensation":"stock_compensation",
            "debt_proceeds":"debt_issuance"}.get(key,key)


def missing(label: str, period: str, reason: str, unit: str = "") -> Datum:
    return Datum(label, period, unit, reason=reason)


def source_datum(fact: Fact) -> Datum:
    v = fact.presentation_value if fact.presentation_value is not None else fact.value
    return Datum(fact.label, fact.end, fact.unit, Decimal(str(v)), fact=fact)


def currency(unit: str) -> bool:
    return len(unit) == 3 and unit.isupper() and unit.isalpha()


def combine(label: str, period: str, unit: str, formula: str, args: tuple[Datum, ...], fn,
            denominator: Datum | None = None, positive_denominator: bool = True) -> Datum:
    problems = [f"{a.label}: {a.reason or 'unavailable'}" for a in args if a.value is None]
    sources = tuple(dict.fromkeys(f for a in args for f in a.sources))
    if len({f.unit for f in sources if currency(f.unit)}) > 1:
        problems.append("Inputs have different currencies; no conversion is assumed.")
    for end in {f.end for f in sources}:
        group = [f for f in sources if f.end == end]
        if len({f.accession for f in group}) > 1:
            problems.append(f"Inputs for {end} come from different filing vintages.")
        if len({f.start for f in group if f.start}) > 1:
            problems.append(f"Inputs for {end} have different duration starts.")
    if denominator and denominator.value is not None:
        threshold = max([Decimal("0.000000001"), *[quantum(f) / 2 for f in denominator.sources]])
        if abs(denominator.value) <= threshold or positive_denominator and denominator.value < 0:
            problems.append("Denominator is nonpositive or too close to zero at available precision.")
    if problems:
        return Datum(label, period, unit, formula=formula, inputs=args, reason=" ".join(dict.fromkeys(problems)))
    try:
        with localcontext() as context:
            context.prec = 28
            result = fn(*(a.value for a in args))
        if not result.is_finite():
            raise InvalidOperation
    except (ArithmeticError, ValueError):
        return Datum(label, period, unit, formula=formula, inputs=args, reason="Calculation is undefined for these inputs.")
    return Datum(label, period, unit, result, formula, args)


def quantum(fact: Fact) -> Decimal:
    try:
        places = int(fact.decimals)
        return Decimal(10) ** (-places) if -15 <= places <= 15 else Decimal(0)
    except (ValueError, TypeError):
        return Decimal(0)


def equivalent(a: Datum, b: Datum) -> bool:
    return bool(a.fact and b.fact and semantic_key(a.fact) == semantic_key(b.fact)
                and a.unit == b.unit and a.fact.dimensions == b.fact.dimensions)


class Calculator:
    def __init__(self, bundle: StatementBundle):
        self.bundle = bundle
        self.periods = sorted(bundle.periods)
        self.selected = [f for rows in bundle.statements.values() for row in rows for f in row.values.values()]
        self.memo: dict[tuple[str, str], Datum] = {}
        self.metric_memo: dict[tuple[str, str], Datum] = {}
        self.definitions = {d.key: d for d in DEFINITIONS}
        self.industrial = bool(len(bundle.company.sic)==4 and bundle.company.sic.isdigit()
                               and not 6000 <= int(bundle.company.sic) <= 6999)

    def get(self, key: str, period: str) -> Datum:
        if (key, period) in self.memo:
            return self.memo[key, period]
        candidates = [f for f in self.selected if f.end == period and not f.dimensions and semantic_key(f) == key]
        # Exact note mappings supplement analytics only; they do not modify statements.
        if not candidates and key in EXTRA_TAGS:
            candidates = [f for f in self.bundle.disclosures if f.end == period and not f.dimensions and semantic_key(f) == key]
            if candidates:
                latest = max((f.filed, f.accession) for f in candidates)
                candidates = [f for f in candidates if (f.filed, f.accession) == latest]
        if not candidates and period not in self.periods:
            candidates = [f for f in self.bundle.raw_facts if f.end == period and not f.dimensions and semantic_key(f) == key]
            if candidates:
                latest = max((f.filed, f.accession) for f in candidates)
                candidates = [f for f in candidates if (f.filed, f.accession) == latest]
        preferred_statement = EXTRA_TAGS.get(key, (None,))[0]
        if key == "net_income":
            preferred_statement = P
        if preferred_statement and any(f.statement == preferred_statement for f in candidates):
            candidates = [f for f in candidates if f.statement == preferred_statement]
        identities = {(f.unit, f.value, f.start, f.accession) for f in candidates}
        if not candidates:
            result = missing(key.replace("_", " "), period, "Required reported input is unavailable or unsupported.")
        elif len(identities) != 1:
            result = missing(key.replace("_", " "), period, "Conflicting input observations or scopes; no value selected.")
        else:
            result = source_datum(max(candidates, key=lambda f: (bool(f.context_id), bool(f.decimals))))
        self.memo[key, period] = result
        return result

    def revenue(self, period: str) -> Datum:
        for key in ("revenue", "net_sales", "contract_revenue"):
            item = self.get(key, period)
            if item.value is not None:
                return item
            if "Conflicting" in item.reason:
                return item
        return missing("Revenue", period, "No unambiguous consolidated revenue basis is available.")

    def prior(self, period: str) -> str | None:
        available = set(self.periods) | {f.end for f in self.bundle.raw_facts}
        before = [p for p in available if p < period and 300 <= (date.fromisoformat(period) - date.fromisoformat(p)).days <= 400]
        return max(before, default=None)

    def avg(self, key: str, period: str) -> Datum:
        previous = self.prior(period)
        if not previous:
            return missing("Average " + key, period, "Consecutive beginning balance is unavailable.")
        a, b = self.get(key, previous), self.get(key, period)
        if a.value is not None and b.value is not None and not equivalent(a, b):
            return missing("Average " + key, period, "Beginning and ending balances use different concepts.")
        return combine("Average " + key, period, b.unit, "({0}+{1})/2", (a, b), lambda x, y: (x+y)/2)

    def days(self, period: str) -> Datum:
        revenue = self.revenue(period)
        if not revenue.fact or not revenue.fact.start or revenue.fact.extraction == "html-table":
            return missing("Fiscal days", period, "An exact reported annual start date is required.", "days")
        count = (date.fromisoformat(period) - date.fromisoformat(revenue.fact.start)).days + 1
        return Datum("Actual inclusive fiscal days", period, "days", Decimal(count), inputs=(revenue,))

    def metric(self, key: str, period: str) -> Datum:
        if (key, period) in self.metric_memo:
            return self.metric_memo[key, period]
        d = self.definitions[key]
        if d.industrial and not self.industrial:
            item = missing(d.label, period, "Industrial-company method withheld: SEC SIC is unknown or identifies a financial business.", d.unit)
        else:
            item = self._metric(d, period)
        self.metric_memo[key, period] = item
        return item

    def _metric(self, d: Definition, p: str) -> Datum:
        get = lambda k: self.get(k, p)
        r = self.revenue(p)
        def calc(formula, args, fn, denom=None):
            unit = next((f.unit for a in args for f in a.sources if currency(f.unit)), "currency") if d.unit == "currency" else d.unit
            return combine(d.label, p, unit, formula, tuple(args), fn, denom)
        def ratio(a, b):
            return calc("{0}/{1}", (a, b), lambda x,y:x/y, b)
        key = d.key
        pairs = {
            "operating_margin": ("operating_income", r), "net_margin": ("net_income", r),
            "sga_intensity": ("selling_general_admin", r), "rd_intensity": ("research_development", r),
            "current_ratio": ("current_assets", get("current_liabilities")),
            "debt_assets": ("debt_total", get("assets")),
            "interest_coverage": ("operating_income", get("interest")),
            "ocf_margin": ("cfo", r), "cash_conversion": ("cfo", get("net_income_total")),
            "roa": ("net_income_total", self.avg("assets", p)),
            "roe": ("common_income", self.avg("common_equity", p)),
            "operating_return": ("operating_income", self.avg("assets", p)),
        }
        if key in pairs:
            a, b = pairs[key]
            return ratio(get(a), b)
        if key == "asset_turnover":
            return ratio(r, self.avg("assets", p))
        if key in {"revenue_growth", "revenue_cagr"}:
            q = p
            for _ in range(3 if key == "revenue_cagr" else 1):
                q = self.prior(q)
                if not q:
                    return missing(d.label, p, "Consecutive historical revenue observations are required.", d.unit)
                if not equivalent(r, self.revenue(q)):
                    return missing(d.label, p, "Revenue scope or currency changed, or an intervening observation is missing.", d.unit)
            old = self.revenue(q)
            if key == "revenue_cagr":
                if r.value is None or r.value <= 0:
                    return missing(d.label, p, "CAGR requires positive endpoint revenue.", d.unit)
                return calc("({0}/{1})^(1/3)-1", (r, old), lambda x,y: (x/y) ** (Decimal(1)/3)-1, old)
            return calc("{0}/{1}-1", (r, old), lambda x,y:x/y-1, old)
        if key == "gross_margin":
            cost, gross = get("cost_of_sales"), get("gross_profit")
            for candidate in (get("net_sales"), get("contract_revenue"), get("revenue")):
                check = combine("Gross profit reconciliation", p, candidate.unit, "{0}-{1}-{2}", (candidate, cost, gross), lambda x,y,z:x-y-z)
                if check.value is not None and abs(check.value) <= sum((quantum(f)/2 for f in check.sources), Decimal("0.000001")):
                    return ratio(gross, candidate)
            return missing(d.label, p, "A compatible revenue/cost/gross-profit relationship could not be verified.", d.unit)
        if key == "quick_ratio":
            a,b,c,e = get("cash"),get("short_term_investments"),get("receivables"),get("current_liabilities")
            return calc("({0}+{1}+{2})/{3}", (a,b,c,e), lambda w,x,y,z:(w+x+y)/z, e)
        if key == "net_debt":
            return calc("{0}-{1}", (get("debt_total"),get("cash")), lambda x,y:x-y)
        if key == "capex_intensity":
            return calc("ABS({0})/{1}", (get("capex"),r), lambda x,y:abs(x)/y,r)
        if key == "ocf_capex":
            return calc("{0}-ABS({1})", (get("cfo"),get("capex")), lambda x,y:x-abs(y))
        if key == "earnings_cash":
            return calc("{0}-{1}", (get("net_income_total"),get("cfo")), lambda x,y:x-y)
        if key == "accrual_assets":
            return ratio(self.metric("earnings_cash",p), self.avg("assets",p))
        if key in {"receivable_days", "inventory_days", "payable_days"}:
            balance = {"receivable_days":"receivables","inventory_days":"inventory","payable_days":"payables"}[key]
            sales = get("net_sales")
            if sales.value is None:
                sales = r
            denominator = sales if key == "receivable_days" else get("cost_of_sales")
            return calc("{0}/{1}*{2}", (self.avg(balance,p),denominator,self.days(p)), lambda x,y,z:x/y*z,denominator)
        if key == "cash_cycle":
            return calc("{0}+{1}-{2}", tuple(self.metric(k,p) for k in ("receivable_days","inventory_days","payable_days")), lambda x,y,z:x+y-z)
        q = self.prior(p)
        if not q:
            return missing(d.label,p,"Prior annual return inputs are unavailable.",d.unit)
        if key == "return_change":
            return calc("{0}-{1}", (self.metric("operating_return",p),self.metric("operating_return",q)),lambda x,y:x-y)
        # Require equivalent revenue across the bridge, even though each year's
        # margin × turnover independently equals its return by construction.
        if not equivalent(r,self.revenue(q)):
            return missing(d.label,p,"Revenue scope changed across the bridge.",d.unit)
        m, old_m = self.metric("operating_margin",p), self.metric("operating_margin",q)
        t, old_t = self.metric("asset_turnover",p), self.metric("asset_turnover",q)
        if key == "margin_contribution":
            return calc("{0}*({1}-{2})", (old_t,m,old_m),lambda a,b,c:a*(b-c))
        if key == "turnover_contribution":
            return calc("{0}*({1}-{2})", (old_m,t,old_t),lambda a,b,c:a*(b-c))
        return calc("({0}-{1})*({2}-{3})",(m,old_m,t,old_t),lambda a,b,c,e:(a-b)*(c-e))


def build_analysis(bundle: StatementBundle) -> Analysis:
    bundle = prepare_presentation(bundle)
    engine = Calculator(bundle)
    rows = [AnalysisRow(d,{p:engine.metric(d.key,p) for p in engine.periods}) for d in DEFINITIONS]
    schedules: dict[str,list[AnalysisRow]] = {name:[] for name in SCHEDULE_KEYS}
    common = []
    for statement, reported in bundle.statements.items():
        for index,row in enumerate(reported):
            keys = {semantic_key(f) for f in row.values.values()}
            for group,wanted in SCHEDULE_KEYS.items():
                if keys & wanted:
                    d = definition(f"{statement}:{index}",row.label,group,"Reported source value",row.unit,"Reported historical disclosure.","No missing movements are inferred; this is not a complete roll-forward.")
                    schedules[group].append(AnalysisRow(d,{p:source_datum(row.values[p]) if p in row.values else missing(row.label,p,"No selected reported observation.",row.unit) for p in engine.periods}))
            if statement in {P,B} and currency(row.unit):
                d = definition(f"common:{statement}:{index}",row.label,statement,"Reported line / " + ("selected revenue" if statement == P else "total assets"),"%","Composition of the reported statement.","Overlapping totals/components are not additive. Denominator scope is recorded in inputs.")
                cells = {}
                for p in engine.periods:
                    a = source_datum(row.values[p]) if p in row.values else missing(row.label,p,"No selected reported observation.")
                    b = engine.revenue(p) if statement == P else engine.get("assets",p)
                    cells[p] = combine(d.label,p,"%","{0}/{1}",(a,b),lambda x,y:x/y,b)
                common.append(AnalysisRow(d,cells))
    # Notes remain separate and preserve full member identity; never add members.
    disclosure_rows = {}
    for f in bundle.disclosures:
        if f.end not in engine.periods or f.section not in schedules:
            continue
        key = (f.section,f.tag,f.unit,f.dimensions,f.start is None)
        disclosure_rows.setdefault(key,{}).setdefault(f.end,[]).append(f)
    for (group,tag,unit,dimensions,instant),values in disclosure_rows.items():
        sample = next(iter(values.values()))[0]
        def readable(value):
            local = value.rsplit(":",1)[-1]
            local = re.sub(r"(?:Axis|Member)$","",local)
            return re.sub(r"(?<=[a-z])(?=[A-Z])"," ",local)
        label = sample.label + (" · " + "; ".join(f"{readable(a)}: {readable(m)}" for a,m in dimensions) if dimensions else " · note disclosure")
        d = definition("note:"+str(len(schedules[group])),label,group,"Reported disclosure",unit,"Annual note disclosure with explicit context.","Dimensions are not assumed additive. Maturity buckets are contractual as-of disclosures.")
        cells = {}
        for p in engine.periods:
            candidates = values.get(p,[])
            latest = max(((f.filed,f.accession) for f in candidates),default=None)
            selected = [f for f in candidates if (f.filed,f.accession)==latest]
            cells[p] = source_datum(max(selected, key=lambda f: (bool(f.context_id), bool(f.decimals)))) if selected and len({(f.value,f.start) for f in selected})==1 else missing(label,p,"No unambiguous annual disclosure.",unit)
        schedules[group].append(AnalysisRow(d,cells))
    checks = validation_checks(engine)
    notes = [
        "Historical calculations only. No forecast, valuation, recommendation or CFA certification.",
        "Revenue basis is selected in order: total revenue, net sales, customer-contract revenue. Growth requires unchanged scope. Inspect every calculation's inputs.",
        "Cash-flow movements and balance-sheet changes are different measures. Schedule groupings do not imply complete roll-forwards.",
        "Advanced NOA/NFO and after-tax RNOA are unavailable without complete operating/financing classifications and tax allocations; no assumptions are inserted.",
        "Peer comparability scoring is not implemented. The De Franco measure needs a separate quarterly earnings/return design.",
        "Institutional acceptance pending independent live-filing verification across representative companies; passed checks are not an audit.",
    ]
    if not engine.industrial:
        notes.append("SEC industry classification is unknown or identifies a financial firm. Industrial-company metrics are withheld; reported schedules remain available.")
    return Analysis(engine.periods,rows,schedules,common,checks,notes)


def validation_checks(engine: Calculator) -> list[Check]:
    checks = []
    for p in engine.periods:
        specs = [
            ("Assets versus reported liabilities and equity",(engine.get("assets",p),engine.get("liabilities_and_equity",p)),"{0}-{1}",lambda a,b:a-b),
            ("Cash movement — cash equivalents",tuple(engine.get(k,p) for k in ("cash_end","cash_begin","cash_change")),"{0}-{1}-{2}",lambda a,b,c:a-b-c),
            ("Cash movement — including restricted cash",tuple(engine.get(k,p) for k in ("restricted_cash_end","restricted_cash_begin","restricted_cash_change")),"{0}-{1}-{2}",lambda a,b,c:a-b-c),
            ("Operating return bridge",tuple(engine.metric(k,p) for k in ("return_change","margin_contribution","turnover_contribution","interaction")),"{0}-{1}-{2}-{3}",lambda a,b,c,d:a-b-c-d),
        ]
        for label,args,formula,fn in specs:
            if label=="Operating return bridge" and not engine.industrial:
                checks.append(Check(p,label,"not applicable",None,None,"Industrial method unavailable for this SIC classification."))
                continue
            value = combine(label,p,"",formula,args,fn)
            tolerance = sum((quantum(f)/2 for f in value.sources),Decimal("0.000001")) if label!="Operating return bridge" else Decimal("0.000000001")
            status = "insufficient information" if value.value is None else "passed" if abs(value.value)<=tolerance else "discrepancy"
            checks.append(Check(p,label,status,value.value,tolerance if value.value is not None else None,value.reason or "Checked compatible selected inputs with explicit rounding tolerance; not an audit."))
    return checks


def display_value(item: Datum) -> str:
    if item.value is None:
        return "—"
    value = item.value
    if item.unit in {"%","pp"}:
        return f"{value*100:,.2f}" + ("%" if item.unit=="%" else " pp")
    if currency(item.unit):
        return f"{value/Decimal(1000000):,.2f} {item.unit}m"
    return f"{value:,.2f}" + ("×" if item.unit=="x" else " days" if item.unit=="days" else "")
