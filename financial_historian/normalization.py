"""Conservative identities for continuous reported statement rows.

These aliases identify a line; they never sum facts or alter the source tag.
Only exact, statement-specific labels are recognized for untagged HTML. Distinct
scopes (current/noncurrent, parent/noncontrolling, continuing/total operations)
remain distinct. Concurrent conflicting aliases are handled by the assembler.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .models import Fact, STATEMENTS


@dataclass(frozen=True)
class Concept:
    key: str
    label: str
    section: str
    order: int
    is_total: bool = False
    supplement: bool = False
    outflow: bool = False


_TAGS: dict[tuple[str, str], Concept] = {}
_LABELS: dict[tuple[str, str], Concept] = {}
_CONCEPTS: dict[tuple[str, str], Concept] = {}


def clean_label(label: str) -> str:
    # Legacy EDGAR files occasionally decode Windows-1252 punctuation as controls.
    label = label.replace("\x92", "’").replace("\x91", "‘").replace("\x96", "–").replace("\x97", "—").strip()
    return re.sub(r"\s*\(Deprecated \d{4}-\d{2}-\d{2}\)", "", label, flags=re.I)


def _label_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_label(label).lower()).strip()


def _register(statement, key, label, section, order, tags=(), labels=(), *, total=False, supplement=False, outflow=False):
    concept = Concept(key, label, section, order, total, supplement, outflow)
    _CONCEPTS[(statement, key)] = concept
    for tag in tags:
        # Explicit namespace required for IFRS aliases; never infer from localname.
        _TAGS[(statement, tag if ":" in tag else "us-gaap:" + tag)] = concept
    for alias in labels:
        _LABELS[(statement, _label_key(alias))] = concept


P, B, C = STATEMENTS
_register(P, "revenue", "Revenue", "Income statement", 10,
          ["Revenues"],
          ["Revenue", "Revenues", "Total revenue", "Total revenues"], total=True, supplement=True)
_register(P, "net_sales", "Net sales", "Income statement", 11,
          ["SalesRevenueNet"], ["Net sales", "Total net sales"], total=True, supplement=True)
_register(P, "contract_revenue", "Customer-contract revenue, excluding assessed tax", "Income statement", 12,
          ["RevenueFromContractWithCustomerExcludingAssessedTax"], total=True, supplement=True)
# Tax-inclusive revenue and product/service components intentionally stay separate.
_register(P, "cost_of_sales", "Cost of sales", "Income statement", 20,
          ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfSales"],
          ["Cost of sales", "Total cost of sales", "Cost of revenue", "Cost of revenues"], supplement=True)
_register(P, "gross_profit", "Gross profit", "Income statement", 30, ["GrossProfit"], ["Gross profit", "Gross margin"], total=True, supplement=True)
_register(P, "research_development", "Research and development", "Operating expenses", 40, ["ResearchAndDevelopmentExpense"], ["Research and development"])
_register(P, "selling_general_admin", "Selling, general and administrative", "Operating expenses", 50, ["SellingGeneralAndAdministrativeExpense"], ["Selling, general and administrative", "Selling, general and administrative expenses"])
_register(P, "selling_marketing", "Sales and marketing", "Operating expenses", 51,
          ["SellingAndMarketingExpense"], ["Sales and marketing", "Selling and marketing"])
_register(P, "general_admin", "General and administrative", "Operating expenses", 52,
          ["GeneralAndAdministrativeExpense"], ["General and administrative"])
_register(P, "purchased_intangible_amortization", "Amortization of purchased intangible assets", "Operating expenses", 55,
          labels=["Amortization of purchased intangible assets"])
_register(P, "restructuring", "Restructuring and other charges", "Operating expenses", 60,
          labels=["Restructuring and other charges"])
_register(P, "operating_expenses", "Total operating expenses", "Operating expenses", 70, ["OperatingExpenses"], ["Operating expenses", "Total operating expenses"], total=True, supplement=True)
_register(P, "operating_income", "Operating income / (loss)", "Income statement", 80, ["OperatingIncomeLoss"], ["Operating income", "Operating income (loss)", "Income from operations", "Operating profit"], total=True, supplement=True)
_register(P, "nonoperating", "Non-operating income / (expense), net", "Income statement", 90, ["NonoperatingIncomeExpense"], ["Other income/(expense), net", "Other income (expense), net", "Non-operating income (expense), net"])
_register(P, "interest", "Interest expense", "Non-operating items", 92,
          ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseNonOperating"], ["Interest expense"])
_register(P, "interest_income", "Interest income", "Non-operating items", 91,
          ["InvestmentIncomeInterest"], ["Interest income"])
_register(P, "interest_dividend_income", "Interest and dividend income", "Non-operating items", 91,
          ["InvestmentIncomeInterestAndDividend"], ["Interest and dividend income"])
_register(P, "pretax_income", "Income / (loss) before tax", "Income statement", 110,
          ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
          ["Income before provision for income taxes", "Income before income taxes", "Income before taxes", "Earnings before income taxes"], total=True, supplement=True)
_register(P, "pretax_before_equity_method", "Income before tax and equity method investments", "Income statement", 111,
          ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"], supplement=True)
_register(P, "tax", "Income tax expense / (benefit)", "Income statement", 120, ["IncomeTaxExpenseBenefit"], ["Provision for income taxes", "Income tax expense", "Income taxes", "Provision for (benefit from) income taxes"], supplement=True)
_register(P, "net_income", "Net income / (loss)", "Income statement", 130, ["NetIncomeLoss"], ["Net income", "Net income (loss)", "Net loss", "Net earnings"], total=True, supplement=True)
_register(P, "eps_basic", "Earnings per share — basic", "Per share data", 150, ["EarningsPerShareBasic"], ["Basic earnings per share", "Earnings per share basic", "Basic net income per share"], supplement=True)
_register(P, "eps_diluted", "Earnings per share — diluted", "Per share data", 160, ["EarningsPerShareDiluted"], ["Diluted earnings per share", "Earnings per share diluted", "Diluted net income per share"], supplement=True)
_register(P, "shares_basic", "Weighted average shares — basic", "Share counts", 170, ["WeightedAverageNumberOfSharesOutstandingBasic"], ["Weighted average shares outstanding basic", "Weighted average basic shares outstanding"], supplement=True)
_register(P, "shares_diluted", "Weighted average shares — diluted", "Share counts", 180, ["WeightedAverageNumberOfDilutedSharesOutstanding"], ["Weighted average diluted shares outstanding", "Weighted average shares outstanding diluted"], supplement=True)
_register(P, "dividends_per_share", "Dividends declared per share", "Per share data", 165, ["CommonStockDividendsPerShareDeclared"], ["Cash dividends declared per share", "Cash dividends declared per common share"])

# Balance sheet rows retain explicitly different current and noncurrent scopes.
_balance_specs = [
 ("cash", "Cash and cash equivalents", "Current assets", 10, ["CashAndCashEquivalentsAtCarryingValue"], ["Cash and cash equivalents"]),
 ("marketable_current", "Marketable securities — current", "Current assets", 20, ["MarketableSecuritiesCurrent"], ["Current marketable securities", "Short-term marketable securities"]),
 ("short_term_investments", "Short-term investments", "Current assets", 21, ["ShortTermInvestments"], ["Short-term investments"]),
 ("receivables", "Accounts receivable, net", "Current assets", 30, ["AccountsReceivableNetCurrent"], ["Accounts receivable, net"]),
 ("nontrade_receivables", "Non-trade receivables — current", "Current assets", 35, ["NontradeReceivablesCurrent"], ["Vendor non-trade receivables"]),
 ("inventory", "Inventories", "Current assets", 40, ["InventoryNet"], ["Inventories", "Inventories, net"]),
 ("other_current_assets", "Other current assets", "Current assets", 50, ["OtherAssetsCurrent"], ["Other current assets"]),
 ("current_assets", "Total current assets", "Current assets", 60, ["AssetsCurrent"], ["Total current assets"]),
 ("marketable_noncurrent", "Marketable securities — noncurrent", "Noncurrent assets", 70, ["MarketableSecuritiesNoncurrent"], ["Non-current marketable securities", "Noncurrent marketable securities", "Long-term marketable securities"]),
 ("ppe", "Property, plant and equipment, net", "Noncurrent assets", 80, ["PropertyPlantAndEquipmentNet"], ["Property, plant and equipment, net", "Property, plant, and equipment, net"]),
 ("goodwill", "Goodwill", "Noncurrent assets", 90, ["Goodwill"], ["Goodwill"]),
 ("intangibles", "Intangible assets, net", "Noncurrent assets", 100, ["IntangibleAssetsNetExcludingGoodwill"], ["Acquired intangible assets, net", "Intangible assets, net"]),
 ("other_noncurrent_assets", "Other noncurrent assets", "Noncurrent assets", 110, ["OtherAssetsNoncurrent"], ["Other non-current assets", "Other noncurrent assets"]),
 ("noncurrent_assets", "Total noncurrent assets", "Noncurrent assets", 120, ["AssetsNoncurrent"], ["Total non-current assets", "Total noncurrent assets"]),
 ("assets", "Total assets", "Assets", 130, ["Assets"], ["Total assets"]),
 ("accounts_payable", "Accounts payable", "Current liabilities", 140, ["AccountsPayableCurrent"], ["Accounts payable"]),
 ("accrued_liabilities", "Accrued liabilities — current", "Current liabilities", 145, ["AccruedLiabilitiesCurrent"], ["Accrued expenses", "Accrued liabilities"]),
 ("other_current_liabilities", "Other current liabilities", "Current liabilities", 150, ["OtherLiabilitiesCurrent"], ["Other current liabilities"]),
 ("contract_liability_current", "Contract liabilities — current", "Current liabilities", 155, ["ContractWithCustomerLiabilityCurrent"], []),
 ("deferred_revenue_current", "Deferred revenue — current", "Current liabilities", 156, ["DeferredRevenueCurrent"], []),
 ("commercial_paper", "Commercial paper", "Current liabilities", 160, ["CommercialPaper"], ["Commercial paper"]),
 ("debt_current", "Long-term debt — current portion", "Current liabilities", 170, ["LongTermDebtCurrent"], ["Current portion of long-term debt"]),
 ("current_assets_debt", "Current debt", "Current liabilities", 171, ["ShortTermDebtCurrent"], ["Current debt"]),
 ("current_liabilities", "Total current liabilities", "Current liabilities", 180, ["LiabilitiesCurrent"], ["Total current liabilities"]),
 ("debt_noncurrent", "Long-term debt — noncurrent", "Noncurrent liabilities", 190, ["LongTermDebtNoncurrent"], ["Long-term debt, net of current portion"]),
 ("long_term_debt", "Long-term debt (source scope)", "Noncurrent liabilities", 191, ["LongTermDebt"], ["Long-term debt"]),
 ("other_noncurrent_liabilities", "Other noncurrent liabilities", "Noncurrent liabilities", 200, ["OtherLiabilitiesNoncurrent"], ["Other non-current liabilities", "Other noncurrent liabilities"]),
 ("noncurrent_liabilities", "Total noncurrent liabilities", "Noncurrent liabilities", 210, ["LiabilitiesNoncurrent"], ["Non-current liabilities", "Total non-current liabilities", "Total noncurrent liabilities"]),
 ("liabilities", "Total liabilities", "Liabilities", 220, ["Liabilities"], ["Total liabilities"]),
 ("common_stock_apic", "Common stock and additional paid-in capital", "Equity", 230, ["CommonStocksIncludingAdditionalPaidInCapital"], ["Common stock and additional paid-in capital"]),
 ("retained_earnings", "Retained earnings / (accumulated deficit)", "Equity", 240, ["RetainedEarningsAccumulatedDeficit"], ["Retained earnings", "Accumulated deficit", "Retained earnings (accumulated deficit)"]),
 ("aoci", "Accumulated other comprehensive income / (loss)", "Equity", 250, ["AccumulatedOtherComprehensiveIncomeLossNetOfTax", "AccumulatedOtherComprehensiveIncomeLoss"], ["Accumulated other comprehensive income (loss)", "Accumulated other comprehensive loss", "Accumulated other comprehensive income", "Accumulated other comprehensive (loss)/income"]),
 ("equity", "Total shareholders’ equity", "Equity", 260, ["StockholdersEquity"], ["Total shareholders' equity", "Total shareholders’ equity", "Total stockholders' equity", "Total stockholders’ equity"]),
 ("equity_including_nci", "Total equity including noncontrolling interests", "Equity", 261, ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], []),
 ("liabilities_and_equity", "Total liabilities and shareholders’ equity", "Equity", 270, ["LiabilitiesAndStockholdersEquity"], ["Total liabilities and shareholders' equity", "Total liabilities and shareholders’ equity", "Total liabilities and stockholders' equity", "Total liabilities and stockholders’ equity"]),
]
_B_TOTALS = {"current_assets", "noncurrent_assets", "assets", "current_liabilities", "noncurrent_liabilities", "liabilities", "equity", "equity_including_nci", "liabilities_and_equity"}
for key, label, section, order, tags, labels in _balance_specs:
    _register(B, key, label, section, order, tags, labels, total=key in _B_TOTALS, supplement=key in _B_TOTALS)

# Cash-flow payment concepts have a positive XBRL debit value. A fallback display
# uses the explicitly defined outflow direction; raw source values stay untouched.
_cash_specs = [
 ("net_income", "Net income / (loss)", "Operating activities", 10, ["NetIncomeLoss"], ["Net income", "Net income (loss)"]),
 ("depreciation", "Depreciation and amortization", "Operating activities", 20, ["DepreciationDepletionAndAmortization"], ["Depreciation and amortization"]),
 ("share_compensation", "Share-based compensation", "Operating activities", 30, ["ShareBasedCompensation"], ["Share-based compensation expense", "Share-based compensation"]),
 ("deferred_tax", "Deferred income tax expense / (benefit)", "Operating activities", 40, ["DeferredIncomeTaxExpenseBenefit"], ["Deferred income tax expense/(benefit)", "Deferred income tax expense"]),
 ("receivables_change", "Change in accounts receivable", "Operating activities", 50, ["IncreaseDecreaseInAccountsReceivable"], ["Accounts receivable, net"]),
 ("nontrade_change", "Change in non-trade receivables", "Operating activities", 55, ["IncreaseDecreaseInOtherReceivables"], ["Vendor non-trade receivables"]),
 ("inventory_change", "Change in inventories", "Operating activities", 60, ["IncreaseDecreaseInInventories"], ["Inventories"]),
 ("other_assets_change", "Change in other operating assets", "Operating activities", 65, ["IncreaseDecreaseInOtherOperatingAssets"], ["Other current and non-current assets"]),
 ("payables_change", "Change in accounts payable", "Operating activities", 70, ["IncreaseDecreaseInAccountsPayable"], ["Accounts payable"]),
 ("other_liabs_change", "Change in other operating liabilities", "Operating activities", 75, ["IncreaseDecreaseInOtherOperatingLiabilities"], ["Other current and non-current liabilities"]),
 ("contract_liability_change", "Change in contract liabilities", "Operating activities", 76, ["IncreaseDecreaseInContractWithCustomerLiability"], []),
 ("cfo", "Cash from / (used in) operating activities", "Operating activities", 90, ["NetCashProvidedByUsedInOperatingActivities"], ["Cash generated by operating activities", "Cash used in operating activities", "Net cash provided by operating activities", "Net cash provided by (used in) operating activities", "Net cash from operating activities"]),
 ("purchases_securities", "Purchases of marketable debt securities", "Investing activities", 100, ["PaymentsToAcquireAvailableForSaleSecuritiesDebt"], ["Purchases of marketable securities"]),
 ("securities_maturities", "Proceeds from maturities of securities", "Investing activities", 110, ["ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities"], ["Proceeds from maturities of marketable securities"]),
 ("securities_sales", "Proceeds from sales of securities", "Investing activities", 120, ["ProceedsFromSaleOfAvailableForSaleSecuritiesDebt"], ["Proceeds from sales of marketable securities"]),
 ("capex", "Purchases of property, plant and equipment", "Investing activities", 130, ["PaymentsToAcquirePropertyPlantAndEquipment"], ["Payments for acquisition of property, plant and equipment", "Purchases of property, plant and equipment", "Payments to acquire property, plant and equipment"]),
 ("acquisitions", "Business acquisitions, net of cash acquired", "Investing activities", 140, ["PaymentsToAcquireBusinessesNetOfCashAcquired"], ["Payments made in connection with business acquisitions, net"]),
 ("cfi", "Cash from / (used in) investing activities", "Investing activities", 170, ["NetCashProvidedByUsedInInvestingActivities"], ["Cash generated by investing activities", "Cash used in investing activities", "Net cash used in investing activities", "Net cash provided by investing activities", "Net cash provided by (used in) investing activities"]),
 ("dividends", "Dividends paid", "Financing activities", 180, ["PaymentsOfDividends"], ["Payments for dividends and dividend equivalents", "Dividends and dividend equivalent rights paid", "Dividends paid"]),
 ("repurchases", "Repurchases of common stock", "Financing activities", 190, ["PaymentsForRepurchaseOfCommonStock"], ["Repurchases of common stock", "Repurchase of common stock"]),
 ("stock_proceeds", "Proceeds from common stock issuance", "Financing activities", 195, ["ProceedsFromIssuanceOfCommonStock"], ["Proceeds from issuance of common stock"]),
 ("debt_proceeds", "Proceeds from long-term debt issuance", "Financing activities", 200, ["ProceedsFromIssuanceOfLongTermDebt"], ["Proceeds from issuance of term debt, net", "Proceeds from issuance of long-term debt, net"]),
 ("debt_repayment", "Repayments of long-term debt", "Financing activities", 210, ["RepaymentsOfLongTermDebt"], ["Repayments of term debt", "Repayments of long-term debt"]),
 ("commercial_paper_net", "Commercial paper issuance / (repayment), net", "Financing activities", 220, ["ProceedsFromRepaymentsOfCommercialPaper"], ["Proceeds from/(Repayments of) commercial paper, net", "Change in commercial paper, net"]),
 ("cff", "Cash from / (used in) financing activities", "Financing activities", 240, ["NetCashProvidedByUsedInFinancingActivities"], ["Cash generated by financing activities", "Cash used in financing activities", "Net cash used in financing activities", "Net cash provided by financing activities", "Net cash provided by (used in) financing activities"]),
 ("cash_change", "Change in cash and cash equivalents", "Cash reconciliation", 250, ["CashAndCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect"], ["Increase/(Decrease) in cash and cash equivalents", "Increase (decrease) in cash and cash equivalents"]),
 ("restricted_cash_change", "Change in cash including restricted cash", "Cash reconciliation", 251, ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect"], ["Increase/(Decrease) in cash, cash equivalents, and restricted cash and cash equivalents"]),
 ("exchange_effect", "Exchange rate effect on cash", "Cash reconciliation", 245, ["EffectOfExchangeRateOnCashAndCashEquivalents"], ["Effect of exchange rate changes on cash and cash equivalents"]),
 ("tax_paid", "Cash paid for income taxes, net", "Supplemental disclosures", 290, ["IncomeTaxesPaidNet"], ["Cash paid for income taxes, net"]),
 ("interest_paid", "Cash paid for interest", "Supplemental disclosures", 300, ["InterestPaidNet"], ["Cash paid for interest"]),
]
_C_TOTALS = {"cfo", "cfi", "cff", "cash_change", "restricted_cash_change"}
_C_SUPPLEMENT = _C_TOTALS | {"capex", "dividends", "repurchases", "exchange_effect"}
_C_OUTFLOWS = {"capex", "dividends", "repurchases", "acquisitions", "purchases_securities", "debt_repayment"}
for key, label, section, order, tags, labels in _cash_specs:
    _register(C, key, label, section, order, tags, labels, total=key in _C_TOTALS, supplement=key in _C_SUPPLEMENT, outflow=key in _C_OUTFLOWS)
for key, label, order, aliases in [
    ("cash_begin", "Cash and cash equivalents — beginning", 260, ["Cash and cash equivalents, beginning of the year", "Cash and cash equivalents, beginning of period"]),
    ("cash_end", "Cash and cash equivalents — ending", 270, ["Cash and cash equivalents, end of the year", "Cash and cash equivalents, end of period"]),
    ("restricted_cash_begin", "Cash including restricted cash — beginning", 261, ["Cash, cash equivalents, and restricted cash and cash equivalents, beginning balances"]),
    ("restricted_cash_end", "Cash including restricted cash — ending", 271, ["Cash, cash equivalents, and restricted cash and cash equivalents, ending balances"]),
]:
    _register(C, key, label, "Cash reconciliation", order, labels=aliases, total=True)

# IFRS concepts are explicit; similarly named US GAAP tags are not automatically
# interchangeable. They share core identities only where scopes are equivalent.
for statement, key, tag in [
    (P, "revenue", "Revenue"), (P, "gross_profit", "GrossProfit"),
    (P, "eps_basic", "BasicEarningsLossPerShare"), (P, "eps_diluted", "DilutedEarningsLossPerShare"),
    (B, "assets", "Assets"), (B, "liabilities", "Liabilities"),
    (B, "equity_including_nci", "Equity"), (B, "liabilities_and_equity", "EquityAndLiabilities"),
    (C, "cfo", "CashFlowsFromUsedInOperatingActivities"), (C, "cfi", "CashFlowsFromUsedInInvestingActivities"),
    (C, "cff", "CashFlowsFromUsedInFinancingActivities"),
]:
    _TAGS[(statement, "ifrs-full:" + tag)] = _CONCEPTS[(statement, key)]

_NOTE_ONLY = {"CommonStockParOrStatedValuePerShare", "CommonStockSharesAuthorized", "PreferredStockParOrStatedValuePerShare", "PreferredStockSharesAuthorized"}


def _unscoped_concept_for(fact: Fact) -> Concept | None:
    # Inline labels provide issuer-specific scope unavailable in companyfacts.
    # A net-sales label is not evidence that a broader Revenues total is equivalent.
    if fact.statement == P and fact.extraction in {"inline-xbrl", "html-table"}:
        label = _label_key(fact.label)
        if label in {"net sales", "total net sales"}:
            return _CONCEPTS[(P, "net_sales")]
        if label in {"total revenue", "total revenues"}:
            return _CONCEPTS[(P, "revenue")]
    if fact.statement == C and fact.row_role in {"cash_begin", "cash_end"}:
        prefix = "restricted_" if "RestrictedCash" in fact.tag or "restricted cash" in fact.label.lower() else ""
        return _CONCEPTS[(C, prefix + fact.row_role)]
    tagged = _TAGS.get((fact.statement, fact.tag))
    if tagged:
        return tagged
    if not fact.tag.startswith("html:"):
        return None
    label = _label_key(fact.label)
    if fact.statement == P and label in {"basic", "diluted"}:
        prefix = "eps_" if fact.unit.endswith("/shares") else "shares_" if fact.unit == "shares" else ""
        return _CONCEPTS.get((P, prefix + label))
    if fact.statement == B and (re.fullmatch(r"accounts receivable less allowances of (?:[0-9 ]+ and [0-9 ]+ respectively|[0-9 ]+ in each period)", label)
                                or re.fullmatch(r"accounts receivable net of allowance(?:s)? for doubtful accounts of [a-z0-9 ]+", label)):
        return _CONCEPTS[(B, "receivables")]
    if fact.statement == B and label in {"marketable securities", "term debt", "deferred revenue"}:
        section = _label_key(fact.section)
        noncurrent = "noncurrent" in section or "non current" in section
        current = noncurrent or "current" in section
        if current:
            key = {"marketable securities": "marketable_noncurrent" if noncurrent else "marketable_current", "term debt": "debt_noncurrent" if noncurrent else "debt_current", "deferred revenue": "deferred_revenue_noncurrent" if noncurrent else "deferred_revenue_current"}[label]
            return _CONCEPTS.get((B, key))
    return _LABELS.get((fact.statement, label))


def concept_for(fact: Fact) -> Concept | None:
    concept = _unscoped_concept_for(fact)
    if not concept or not fact.tag.startswith("html:") or not fact.section:
        return concept
    actual, expected = _label_key(fact.section), _label_key(concept.section)
    if fact.statement == B:
        def scope(section):
            if "non current" in section or "noncurrent" in section:
                return "noncurrent"
            return "current" if "current" in section else ""
        if scope(actual) and scope(expected) and scope(actual) != scope(expected):
            return None
        def category(section):
            return next((name for name in ("assets", "liabilities", "equity") if name in section), "")
        if category(actual) and category(expected) and category(actual) != category(expected):
            return None
    if fact.statement == C:
        activities = {"operating activities", "investing activities", "financing activities"}
        if actual in activities and expected in activities and actual != expected:
            return None
    return concept


def concept_key(fact: Fact) -> str:
    concept = concept_for(fact)
    return concept.key if concept else fact.tag


def row_identity(fact: Fact) -> tuple[str, str, str]:
    concept = concept_for(fact)
    # Known identities already include the scope. Unknown HTML labels and custom
    # tags retain source sections, preventing separate "Other" rows from merging.
    return (concept.key if concept else fact.tag, fact.unit, "" if concept else fact.section + "|" + fact.row_role)


def include_on_face(fact: Fact) -> bool:
    return not (fact.tag.startswith("us-gaap:") and fact.tag.split(":", 1)[1] in _NOTE_ONLY)


# Debit-nature payment / asset-increase concepts require the opposite sign
# when used as a cash-flow contribution. Do not infer this from a tag prefix.
_CASH_FLOW_NEGATED_TAGS = {
    "us-gaap:" + local for local in (
        "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireInvestments",
        "PaymentsToAcquireShortTermInvestments", "PaymentsToAcquireAvailableForSaleSecuritiesDebt",
        "PaymentsToAcquireOtherInvestments", "PaymentsForRepurchaseOfCommonStock",
        "PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsForRepurchaseOfEquity",
        "RepaymentsOfLongTermDebt", "PaymentsOfFinanceLeasePrincipal",
        "PaymentsRelatedToTaxWithholdingForShareBasedCompensation",
        "PaymentsForProceedsFromOtherInvestingActivities", "IncreaseDecreaseInAccountsReceivable",
        "IncreaseDecreaseInOtherReceivables", "IncreaseDecreaseInInventories",
        "IncreaseDecreaseInOtherOperatingAssets", "OtherNoncashIncomeExpense",
    )
}


def fallback_presentation(fact: Fact) -> float | None:
    if fact.presentation_value is not None:
        return fact.presentation_value
    concept = concept_for(fact)
    if fact.statement == C and fact.extraction in {"companyfacts", "xbrl-instance"} and (fact.tag in _CASH_FLOW_NEGATED_TAGS or concept and concept.outflow):
        return -fact.value
    return None


def row_order(fact: Fact) -> tuple[int, int]:
    concept = concept_for(fact)
    order = concept.order if concept else 1000
    section = _label_key(concept.section if concept else fact.section)
    if fact.statement == B:
        groups = {"current assets":10,"noncurrent assets":20,"non current assets":20,
                  "assets":30,"current liabilities":40,"noncurrent liabilities":50,
                  "non current liabilities":50,"liabilities":60,"equity":70}
        return groups.get(section,90),order
    if fact.statement == C:
        return {"operating activities":10,"investing activities":20,
                "financing activities":30,"cash reconciliation":40}.get(section,90),order
    if concept:
        group = 10 if order<=30 else 20 if order<=70 else 30 if order<=80 else 40 if order<110 else 50 if order<150 else 60 if order<170 else 70
    else:
        group = {"net sales":10,"cost of sales":10,"operating expenses":20,
                 "non operating items":40,"per share data":60,"share counts":70}.get(section,90)
    return group,order

for key, label, order, tag in [
    ("cfo_continuing", "Operating cash flow — continuing operations", 91, "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    ("cfi_continuing", "Investing cash flow — continuing operations", 171, "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations"),
    ("cff_continuing", "Financing cash flow — continuing operations", 241, "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations"),
]:
    _register(C, key, label, {"cfo_continuing": "Operating activities", "cfi_continuing": "Investing activities", "cff_continuing": "Financing activities"}[key], order, [tag], total=True, supplement=True)

_register(B, "deferred_revenue_noncurrent", "Deferred revenue — noncurrent", "Noncurrent liabilities", 198,
          ["DeferredRevenueNoncurrent"], ["Deferred revenue, non-current", "Deferred revenue, noncurrent", "Non-current deferred revenue"])
_register(B, "contract_liability_noncurrent", "Contract liabilities — noncurrent", "Noncurrent liabilities", 197,
          ["ContractWithCustomerLiabilityNoncurrent"])
for key, label, section, order, tag in [
    ("other_noncash", "Other noncash income / (expense)", "Operating activities", 45, "OtherNoncashIncomeExpense"),
    ("other_investing", "Other investing cash flows", "Investing activities", 165, "PaymentsForProceedsFromOtherInvestingActivities"),
    ("other_financing", "Other financing cash flows", "Financing activities", 235, "ProceedsFromPaymentsForOtherFinancingActivities"),
    ("equity_tax_withholding", "Tax withholding on share-based awards", "Financing activities", 175, "PaymentsRelatedToTaxWithholdingForShareBasedCompensation"),
]:
    _register(C, key, label, section, order, [tag])

# Productive assets can include a broader scope than PP&E. Keep a distinct line
# while allowing a standardized observation to repair a partial native table.
_register(C, "productive_assets", "Purchases of productive assets", "Investing activities", 131,
          ["PaymentsToAcquireProductiveAssets"], supplement=True, outflow=True)
