"""Conservative, source-preserving annual SEC financial statement extraction.

Inline XBRL is read only from explicitly headed consolidated statement tables.
The SEC companyfacts endpoint is a useful fallback, but has no presentation tree.
Verified equivalent concepts can share historical rows; distinct scopes remain
separate and source facts are never added into invented statement totals.
"""
from __future__ import annotations

import calendar
import math
import re
from collections import defaultdict
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable

from lxml import etree, html

from .models import Company, CoverageRecord, Fact, Filing, STATEMENTS, StatementBundle, StatementRow


ANNUAL_FORMS = {"10-K", "10-K/A", "10-K405", "10-K405/A", "10-KT", "10-KT/A", "20-F", "20-F/A", "40-F", "40-F/A"}

# This is a classification list, not a standardized chart of accounts. Alternative
# concepts remain distinct: "Revenues" and contract revenue may describe different
# scopes, and adding them would often double count.
_INCOME = """
Revenues Revenue SalesRevenueNet SalesRevenueGoodsNet SalesRevenueServicesNet
RevenueFromContractWithCustomerExcludingAssessedTax RevenueFromContractWithCustomerIncludingAssessedTax
RevenueFromContractWithCustomer RevenueFromSaleOfGoods RevenueFromRenderingOfServices
CostOfRevenue CostOfGoodsAndServicesSold CostOfGoodsSold CostOfSales GrossProfit
ResearchAndDevelopmentExpense SellingGeneralAndAdministrativeExpense SellingAndMarketingExpense
GeneralAndAdministrativeExpense OperatingExpenses CostsAndExpenses OperatingIncomeLoss
IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest
IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments
IncomeTaxExpenseBenefit IncomeLossFromContinuingOperations NetIncomeLoss NetIncomeLossAvailableToCommonStockholdersBasic
ProfitLoss NetIncomeLossAttributableToParent NetIncomeLossAttributableToNoncontrollingInterest
ProfitLossAttributableToOwnersOfParent ProfitLossAttributableToNoncontrollingInterests
EarningsPerShareBasic EarningsPerShareDiluted BasicEarningsLossPerShare DilutedEarningsLossPerShare
WeightedAverageNumberOfSharesOutstandingBasic WeightedAverageNumberOfDilutedSharesOutstanding
WeightedAverageNumberOfOrdinarySharesOutstandingBasic WeightedAverageNumberOfOrdinarySharesOutstandingDiluted
InterestExpense InterestExpenseNonOperating InterestIncomeExpenseNonoperatingNet InvestmentIncomeInterest
InterestAndDebtExpense InterestIncome OtherNonoperatingIncomeExpense OtherOperatingIncomeExpenseNet
NonoperatingIncomeExpense EquityMethodInvestmentsIncomeLoss IncomeLossFromDiscontinuedOperationsNetOfTax
RestructuringAndRelatedCostIncurredInPeriod DepreciationDepletionAndAmortization DepreciationDepletionAndAmortizationExpense
ImpairmentOfLongLivedAssets AssetImpairmentCharges GainLossOnSaleOfAssetsNet GainLossOnSaleOfBusiness
IncomeTaxExpense ProfitLossBeforeTax ProfitLossFromContinuingOperations FinanceCosts FinanceIncome
AdministrativeExpense DistributionCosts OtherExpense OtherIncome
""".split()
_BALANCE = """
Assets AssetsCurrent AssetsNoncurrent CashAndCashEquivalentsAtCarryingValue CashAndCashEquivalents
CashCashEquivalentsAndShortTermInvestments ShortTermInvestments MarketableSecuritiesCurrent
AccountsReceivableNetCurrent AccountsNotesAndOtherReceivablesNetCurrent AccountsReceivableNet
TradeAndOtherCurrentReceivables InventoryNet Inventories PrepaidExpenseCurrent OtherAssetsCurrent
PropertyPlantAndEquipmentNet PropertyPlantAndEquipment Goodwill IntangibleAssetsNetExcludingGoodwill
FiniteLivedIntangibleAssetsNet OtherIntangibleAssetsNet IntangibleAssets GoodwillAndIntangibleAssetsNet
OperatingLeaseRightOfUseAsset FinanceLeaseRightOfUseAsset LongTermInvestments DeferredIncomeTaxAssetsNet
OtherAssetsNoncurrent Liabilities LiabilitiesCurrent LiabilitiesNoncurrent AccountsPayableCurrent
AccountsPayableAndAccruedLiabilitiesCurrent TradeAndOtherCurrentPayables AccruedLiabilitiesCurrent
AccruedIncomeTaxesCurrent ShortTermBorrowings ShortTermDebtCurrent LongTermDebtCurrent
LongTermDebtNoncurrent LongTermDebt LongTermDebtAndFinanceLeaseObligationsCurrent
LongTermDebtAndFinanceLeaseObligationsNoncurrent OperatingLeaseLiabilityCurrent OperatingLeaseLiabilityNoncurrent
FinanceLeaseLiabilityCurrent FinanceLeaseLiabilityNoncurrent DeferredRevenueCurrent ContractWithCustomerLiabilityCurrent
DeferredRevenueNoncurrent ContractWithCustomerLiabilityNoncurrent OtherLiabilitiesCurrent OtherLiabilitiesNoncurrent
DeferredIncomeTaxLiabilitiesNet StockholdersEquity StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest
CommonStockValue CommonStocksIncludingAdditionalPaidInCapital AdditionalPaidInCapital RetainedEarningsAccumulatedDeficit
TreasuryStockValue AccumulatedOtherComprehensiveIncomeLoss MinorityInterest LiabilitiesAndStockholdersEquity
CommonStockSharesOutstanding CommonStockSharesIssued PreferredStockValue PreferredStockSharesOutstanding
NoncontrollingInterestInConsolidatedEntity Equity EquityAttributableToOwnersOfParent
EquityAndLiabilities CurrentAssets NoncurrentAssets CurrentLiabilities NoncurrentLiabilities
IssuedCapital SharePremium RetainedEarnings TreasuryShares CurrentBorrowings NoncurrentBorrowings
CurrentProvisions NoncurrentProvisions DeferredTaxAssets DeferredTaxLiabilities
""".split()
_CASH = """
NetCashProvidedByUsedInOperatingActivities NetCashProvidedByUsedInOperatingActivitiesContinuingOperations
NetCashProvidedByUsedInInvestingActivities NetCashProvidedByUsedInInvestingActivitiesContinuingOperations
NetCashProvidedByUsedInFinancingActivities NetCashProvidedByUsedInFinancingActivitiesContinuingOperations
CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect
CashAndCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect
EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents
EffectOfExchangeRateOnCashAndCashEquivalents PaymentsToAcquirePropertyPlantAndEquipment
PaymentsToAcquireProductiveAssets PaymentsToAcquireBusinessesNetOfCashAcquired
PaymentsToAcquireInvestments PaymentsToAcquireShortTermInvestments PaymentsToAcquireAvailableForSaleSecuritiesDebt
ProceedsFromSaleOfPropertyPlantAndEquipment ProceedsFromSaleOfAvailableForSaleSecuritiesDebt
ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities ProceedsFromSaleOfShortTermInvestments
ProceedsFromStockOptionsExercised ProceedsFromIssuanceOfCommonStock PaymentsForRepurchaseOfCommonStock
PaymentsOfDividends PaymentsOfDividendsCommonStock PaymentsForRepurchaseOfEquity
ProceedsFromIssuanceOfLongTermDebt RepaymentsOfLongTermDebt ProceedsFromRepaymentsOfShortTermDebt
ShareBasedCompensation DeferredIncomeTaxExpenseBenefit IncreaseDecreaseInAccountsReceivable
IncreaseDecreaseInInventories IncreaseDecreaseInAccountsPayable IncreaseDecreaseInOtherOperatingCapitalNet
PaymentsOfFinanceLeasePrincipal CashFlowsFromUsedInOperatingActivities CashFlowsFromUsedInInvestingActivities
CashFlowsFromUsedInFinancingActivities IncreaseDecreaseInCashAndCashEquivalents
EffectOfExchangeRateChangesOnCashAndCashEquivalents PurchaseOfPropertyPlantAndEquipment
DividendsPaid InterestPaid IncomeTaxesPaidRefund
""".split()
_TAG_STATEMENT = {**dict.fromkeys(_INCOME, STATEMENTS[0]), **dict.fromkeys(_BALANCE, STATEMENTS[1]), **dict.fromkeys(_CASH, STATEMENTS[2])}
_CP1252_PUNCTUATION = {code: bytes([code]).decode("cp1252") for code in range(128, 160) if code not in {129, 141, 143, 144, 157}}


def _local(name: str) -> str:
    if not isinstance(name, str):
        return ""
    return name.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()


def _text(node) -> str:
    if not isinstance(node.tag, str):
        return ""
    # Styled spans may split a word ("INC" + "OME") without a whitespace
    # boundary. Preserve that text rather than inserting spaces inside words.
    text = "".join(node.itertext())
    # Old SEC HTML often has Windows-1252 punctuation without a charset. lxml
    # then exposes control-code characters, such as \x92, in company labels.
    text = text.translate(_CP1252_PUNCTUATION)
    return re.sub(r"\s+", " ", text).strip()


def _attr(node, key: str, default: str = "") -> str:
    return next((value for name, value in node.attrib.items() if _local(name) == key.lower()), default)


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except (ValueError, TypeError):
        return None


def _annual_duration(start: str | None, end: str) -> bool:
    first, last = _date(start), _date(end)
    return bool(first and last and 300 <= (last - first).days + 1 <= 400)


def _valid_end(end: str, filing: Filing) -> bool:
    last = _date(end)
    reported = _date(filing.report_date)
    filed = _date(filing.filed)
    return bool(last and (not reported or last <= reported) and (not filed or last <= filed))


def _contexts(root) -> dict[str, tuple[str | None, str]]:
    contexts = {}
    for node in root.iter():
        if not isinstance(node.tag, str) or _local(node.tag) != "context":
            continue
        # Segment and scenario dimensions are not consolidated observations.
        if any(_local(child.tag) in {"explicitmember", "typedmember", "segment", "scenario"} for child in node.iter() if isinstance(child.tag, str)):
            continue
        parts = {_local(child.tag): _text(child) for child in node.iter() if isinstance(child.tag, str) and _local(child.tag) in {"startdate", "enddate", "instant"}}
        end = parts.get("enddate") or parts.get("instant")
        if end and _date(end):
            contexts[_attr(node, "id")] = (parts.get("startdate"), end[:10])
    return contexts


def _measure(text: str) -> str:
    part = text.strip().rsplit(":", 1)[-1]
    return "shares" if part.lower() == "shares" else "pure" if part.lower() == "pure" else part.upper()


def _units(root) -> dict[str, str]:
    result = {}
    for node in root.iter():
        if not isinstance(node.tag, str) or _local(node.tag) != "unit":
            continue
        divided = next((child for child in node.iter() if isinstance(child.tag, str) and _local(child.tag) == "divide"), None)
        if divided is not None:
            numerator = denominator = ""
            for child in divided:
                names = [_measure(_text(measure)) for measure in child.iter() if isinstance(measure.tag, str) and _local(measure.tag) == "measure"]
                if len(names) != 1:
                    continue
                if _local(child.tag) == "unitnumerator":
                    numerator = names[0]
                if _local(child.tag) == "unitdenominator":
                    denominator = names[0]
            if numerator and denominator:
                result[_attr(node, "id")] = numerator + "/" + denominator
        else:
            measures = [_measure(_text(child)) for child in node.iter() if isinstance(child.tag, str) and _local(child.tag) == "measure"]
            if len(measures) == 1:
                result[_attr(node, "id")] = measures[0]
    return result


def _number(text: str, *, transform: str = "", sign: str = "", scale: str = "0") -> float | None:
    token = re.sub(r"\s+", "", text).replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    token = re.sub(r"[$€£¥]", "", token)
    if token in {"-", "--"}:
        if token == "-" and transform.rsplit(":", 1)[-1].replace("-", "").lower() in {"zerodash", "numdash", "fixedzero"}:
            token = "0"
        else:
            return None
    parentheses = token.startswith("(") and token.endswith(")")
    if parentheses:
        token = token[1:-1]
    if "commadecimal" in transform.replace("-", "").lower():
        token = token.replace(".", "").replace(",", ".")
    else:
        token = token.replace(",", "")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", token):
        return None
    try:
        exponent = int(scale)
        if not -20 <= exponent <= 20:
            return None
        amount = Decimal(token) * (Decimal(10) ** exponent)
        if parentheses or sign == "-":
            amount = -abs(amount)
        value = float(amount)
        return value if math.isfinite(value) else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _fact_text(node) -> str:
    # ix:exclude appears in visible text but must not contribute to the fact value.
    parts = [node.text or ""]
    for child in node:
        if not isinstance(child.tag, str) or _local(child.tag) != "exclude":
            parts.append(_fact_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


_TITLES = (
    (STATEMENTS[2], r"consolidated\s+(?:statements?\s+of\s+cash\s+flows?|cash\s+flow\s+statements?)"),
    (STATEMENTS[1], r"consolidated\s+(?:balance\s+sheets?|statements?\s+of\s+financial\s+(?:position|condition))"),
    (STATEMENTS[0], r"consolidated\s+(?:statements?\s+of\s+(?:operations|income|earnings|profit(?:\s+(?:and|or)\s+loss)?)|income\s+statements?)"),
)


def _heading(text: str, allow_unprefixed: bool = False) -> str | None:
    if len(text) > 500 or re.search(r"\b(?:notes?|segments?|parent\s+company|unaudited|supplementary|selected|analysis|summari[sz]ed|summary|fair\s+value|amounts\s+netted|discussion|refer\s+to|following|affect|our|included|recorded|recognized|reflect|include|shows?)\b", text, re.I):
        return None
    hits = [statement for statement, pattern in _TITLES if re.search(pattern, text, re.I)]
    if not hits and allow_unprefixed:
        normalized = text.strip(" .:").lower()
        if normalized in {"income statements", "statements of income", "statements of operations", "statements of earnings"}:
            hits = [STATEMENTS[0]]
        elif normalized in {"balance sheets", "statements of financial position", "statements of financial condition"}:
            hits = [STATEMENTS[1]]
        elif normalized in {"cash flow statements", "cash flows statements", "statements of cash flows"}:
            hits = [STATEMENTS[2]]
    return hits[0] if len(hits) == 1 else None


def _table_statement(table, allow_unprefixed: bool = False) -> tuple[str | None, str]:
    rows = table.xpath("./tr|./thead/tr|./tbody/tr")
    # Only heading rows: looking at a whole statement could match a source-note
    # reference, and treating a note table as a main statement is worse than a gap.
    prefix = " ".join(_text(row) for row in rows[:4])[:500]
    if re.search(r"\b(?:selected|summari[sz]ed|summary|analysis|fair\s+value)\b", prefix, re.I):
        return None, prefix
    statement = _heading(prefix)
    if statement:
        return statement, prefix
    block = table
    nearby = []
    for _ in range(4):
        previous = block.getprevious()
        for _ in range(6):
            if previous is None:
                break
            text = _text(previous)
            if not text or re.fullmatch(r"[\d\s\W]+", text):
                previous = previous.getprevious()
                continue
            # Do not jump over another table or a substantive paragraph looking
            # for a stale statement heading earlier in the report.
            if _local(previous.tag) == "table" or len(text) > 350 or re.search(r"\b(?:notes?|segments?)\b", text, re.I):
                return None, " ".join(nearby)
            nearby.insert(0, text)
            if found := _heading(text, allow_unprefixed):
                return found, " ".join(nearby) + " " + prefix
            if re.search(r"consolidated|statements?\s+of|balance\s+sheets?", text, re.I):
                return None, " ".join(nearby)
            previous = previous.getprevious()
        block = block.getparent()
        if block is None or _local(block.tag) in {"body", "html"}:
            break
    return None, " ".join(nearby)


def _nearest(node, name: str):
    return next((ancestor for ancestor in node.iterancestors() if isinstance(ancestor.tag, str) and _local(ancestor.tag) == name), None)


def _presentation_value(node) -> float | None:
    cell = _nearest(node, "td")
    if cell is None or sum(isinstance(child.tag, str) and _local(child.tag) == "nonfraction" for child in cell.iter()) != 1:
        return None
    text = _fact_text(cell)
    # Some filings place '(' and ')' in separate table cells around the number.
    # Read only neighboring symbol cells, never a row label or a second value.
    before, after = cell.getprevious(), cell.getnext()
    for _ in range(3):
        if before is None or _local(before.tag) not in {"td", "th"}:
            break
        symbol = _text(before)
        if symbol and not re.fullmatch(r"[$€£¥(+\-\u2212\s]+", symbol):
            break
        text = symbol + text
        before = before.getprevious()
    for _ in range(3):
        if after is None or _local(after.tag) not in {"td", "th"}:
            break
        symbol = _text(after)
        if symbol and not re.fullmatch(r"[)\s]+", symbol):
            break
        text += symbol
        after = after.getnext()
    return _number(text, transform=_attr(node, "format"), scale=_attr(node, "scale", "0"))


def _label_cell(row):
    if row is None:
        return None
    for cell in row.xpath("./td|./th"):
        label = _text(cell).strip(" :\u00a0")
        if re.search(r"[A-Za-z]", label) and not re.fullmatch(r"[A-Z]{3}|\d{4}", label):
            return cell
    return None


def _row_label(node, tag: str) -> str:
    row = _nearest(node, "tr")
    if row is not None:
        cell = _label_cell(row)
        if cell is not None:
            return _text(cell).strip(" :\u00a0")
    local = tag.rsplit(":", 1)[-1]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", local)


def _section_heading(label: str, statement: str) -> str | None:
    """Recognize presentation groups, without treating arbitrary prose as one."""
    label = re.sub(r"\s+", " ", label).strip(" :.").lower()
    if statement == STATEMENTS[2]:
        if re.search(r"^supplemental\b", label):
            return "Supplemental disclosures"
        for activity in ("operating", "investing", "financing"):
            if re.fullmatch(rf"(?:cash flows? (?:from|used in|provided by) )?{activity} activities", label):
                return activity.capitalize() + " activities"
    elif statement == STATEMENTS[1]:
        if re.fullmatch(r"(?:stockholders|shareholders|owners)[’']? equity(?: \(deficit\))?", label):
            return "Equity"
        for name in ("current assets", "noncurrent assets", "non-current assets", "current liabilities", "noncurrent liabilities", "non-current liabilities", "assets", "liabilities"):
            if label == name:
                return name.replace("noncurrent", "non-current").capitalize()
    elif statement == STATEMENTS[0]:
        if re.search(r"weighted.average.*shares|shares.*(?:used|computing|calculation)", label):
            return "Weighted average shares"
        if re.search(r"(?:earnings|income|loss).*per\s+(?:common\s+)?share|^per share", label):
            return "Earnings per share"
        if label in {"operating expenses", "cost of sales", "cost of revenue", "net sales", "revenue", "revenues"}:
            return label.capitalize()
    return None


def _section_after_total(label: str, statement: str, current: str) -> str:
    if statement != STATEMENTS[1]:
        return current
    normalized = label.lower().strip(" :.")
    if normalized == "total current assets":
        return "Non-current assets"
    if normalized == "total current liabilities":
        return "Non-current liabilities"
    if normalized == "total assets":
        return "Liabilities"
    if normalized == "total liabilities":
        return "Equity"
    return current


def _inline_sections(table, statement: str) -> dict:
    sections = {}
    current = ""
    for row in table.xpath("./tr|./thead/tr|./tbody/tr"):
        label_cell = _label_cell(row)
        if label_cell is None:
            continue
        label = _text(label_cell).strip(" :\u00a0")
        data_nodes = [node for node in row.iter() if isinstance(node.tag, str) and _local(node.tag) == "nonfraction" and _nearest(node, "td") is not label_cell]
        if not data_nodes:
            current = _section_heading(label, statement) or current
        sections[row] = current
        if data_nodes:
            current = _section_after_total(label, statement, current)
    return sections


def _cash_column_periods(nodes, contexts, filing: Filing) -> dict[int, tuple[str, str]]:
    """Map physical cash-flow columns only where annual contexts agree exactly."""
    by_column = defaultdict(set)
    for node in nodes:
        context = contexts.get(_attr(node, "contextref"))
        if not context or not _annual_duration(*context) or not _valid_end(context[1], filing):
            continue
        row, cell = _nearest(node, "tr"), _nearest(node, "td")
        if row is None or cell is None:
            continue
        for column, candidate in enumerate(_grid_cells(row)):
            if candidate is cell:
                by_column[column].add(context)
    return {column: next(iter(periods)) for column, periods in by_column.items() if len(periods) == 1}


def _cash_instant_period(node, instant: str, label: str, tag: str, columns: dict[int, tuple[str, str]]) -> tuple[str, str, str] | None:
    if "cash" not in tag.lower() and "cash" not in label.lower():
        return None
    if re.search(r"\bbeginning\b|\bstart\s+of\s+(?:the\s+)?(?:year|period)\b", label, re.I):
        role = "cash_begin"
    elif re.search(r"\bending\b|\bend\s+of\s+(?:the\s+)?(?:year|period)\b", label, re.I):
        role = "cash_end"
    else:
        return None
    row, cell = _nearest(node, "tr"), _nearest(node, "td")
    if row is None or cell is None:
        return None
    periods = {columns[column] for column, candidate in enumerate(_grid_cells(row)) if candidate is cell and column in columns}
    if len(periods) != 1:
        return None
    start, end = next(iter(periods))
    expected = (_date(start) - timedelta(days=1)).isoformat() if role == "cash_begin" else end
    return (start, end, role) if instant == expected else None


def _deduplicate(facts: Iterable[Fact]) -> list[Fact]:
    seen = set()
    result = []
    for fact in facts:
        key = (fact.statement, fact.tag, fact.unit, fact.start, fact.end, fact.accession, fact.value, fact.presentation_value, fact.row_role, fact.source_instant, fact.section)
        if key not in seen:
            seen.add(key)
            result.append(fact)
    return result


def parse_filing_html(content: bytes, filing: Filing) -> list[Fact]:
    """Read annual facts inside identifiable main consolidated statement tables.

    Notes, subsidiary/segment contexts, quarterly durations, nil facts, and
    unparseable numbers are omitted. Omission is an explicit coverage gap in the
    caller; no fabricated zeroes, extrapolation, or OCR guesses are returned.
    """
    if filing.form.upper() not in ANNUAL_FORMS:
        return []
    try:
        # UTF-8 without a meta charset is common in SEC files. Decode it with an
        # explicit parser; otherwise leave legacy byte encoding to lxml.
        try:
            content.decode("utf-8")
            parser = html.HTMLParser(encoding="utf-8")
        except UnicodeDecodeError:
            parser = html.HTMLParser()
        root = html.fromstring(content, parser=parser)
    except (etree.ParserError, ValueError):
        return []
    contexts, units = _contexts(root), _units(root)
    annual_ends = {end for start, end in contexts.values() if _annual_duration(start, end) and _valid_end(end, filing)}
    if _date(filing.report_date):
        annual_ends.add(filing.report_date)
    facts = []
    financial_section = seen_main = in_notes = False
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        name = _local(element.tag)
        if name in {"p", "h1", "h2", "h3", "h4", "div"} and len(element) < 30:
            title = _text(element)
            if len(title) < 180 and not any(_local(child.tag) == "a" and child.get("href") for child in element.iter() if isinstance(child.tag, str)):
                if re.match(r"^item\s*8\b.*financial\s+statements|^financial\s+statements$|^consolidated\s+financial\s+statements$", title, re.I):
                    financial_section = True
                    in_notes = False
                elif re.match(r"^item\s*(?:[1-7]|9|1[0-6])\b", title, re.I):
                    financial_section = False
                if (seen_main or not title.endswith(":")) and re.fullmatch(r"notes\s+to\s+(?:the\s+)?(?:consolidated\s+)?financial\s+statements[:.]?", title, re.I):
                    in_notes = True
        if name != "table" or in_notes:
            continue
        table = element
        statement, heading = _table_statement(table, financial_section)
        if not statement:
            continue
        inline_nodes = [node for node in table.iter() if isinstance(node.tag, str) and _local(node.tag) == "nonfraction" and _nearest(node, "table") is table]
        if not inline_nodes:
            old_facts = _parse_untagged_table(table, statement, heading, filing)
            facts.extend(old_facts)
            seen_main |= bool(old_facts)
            continue
        cash_columns = _cash_column_periods(inline_nodes, contexts, filing) if statement == STATEMENTS[2] else {}
        sections = _inline_sections(table, statement)
        for node in inline_nodes:
            row = _nearest(node, "tr")
            if _nearest(node, "td") is _label_cell(row):
                # Share authorizations and par values embedded in a common-stock
                # label are disclosures, not the monetary statement cell.
                continue
            context = contexts.get(_attr(node, "contextref"))
            unit = units.get(_attr(node, "unitref"))
            if not context or not unit or _attr(node, "nil").lower() in {"true", "1"}:
                continue
            start, end = context
            tag = _attr(node, "name")
            label = _row_label(node, tag)
            row_role, source_instant = "", None
            if not _valid_end(end, filing):
                continue
            if statement == STATEMENTS[1]:
                if start or end not in annual_ends:
                    continue
            elif not _annual_duration(start, end):
                mapped = _cash_instant_period(node, end, label, tag, cash_columns) if statement == STATEMENTS[2] and start is None else None
                if not mapped:
                    continue
                source_instant = end
                start, end, row_role = mapped
            value = _number(_fact_text(node), transform=_attr(node, "format"), sign=_attr(node, "sign"), scale=_attr(node, "scale", "0"))
            if value is None or not tag:
                continue
            presentation_value = _presentation_value(node)
            explanation = "Instant cash balance assigned to its verified annual statement column; original context date is recorded separately." if row_role else ""
            facts.append(Fact(tag, label, unit, value, start, end, filing.accession, filing.filed, filing.form, filing.source_url, statement, "inline-xbrl", selection_reason=explanation, presentation_value=presentation_value, row_role=row_role, source_instant=source_instant, section=sections.get(row, "")))
            seen_main = True
    return _deduplicate(facts)


def parse_xbrl_instance(content: bytes, filing: Filing) -> list[Fact]:
    """Fallback for standard instance concepts; custom role placement is unknown."""
    if filing.form.upper() not in ANNUAL_FORMS:
        return []
    try:
        root = etree.fromstring(content, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except (etree.XMLSyntaxError, ValueError):
        return []
    contexts, units = _contexts(root), _units(root)
    annual_ends = {end for start, end in contexts.values() if _annual_duration(start, end) and _valid_end(end, filing)} | {filing.report_date}
    facts = []
    for node in root.iter():
        if not isinstance(node.tag, str) or not _attr(node, "contextref"):
            continue
        qname = etree.QName(node)
        namespace = qname.namespace or ""
        if "us-gaap" not in namespace and "ifrs" not in namespace:
            continue
        statement = _TAG_STATEMENT.get(qname.localname)
        context, unit = contexts.get(_attr(node, "contextref")), units.get(_attr(node, "unitref"))
        if not statement or not context or not unit or _attr(node, "nil").lower() in {"true", "1"}:
            continue
        start, end = context
        if not _valid_end(end, filing) or (statement == STATEMENTS[1] and (start or end not in annual_ends)) or (statement != STATEMENTS[1] and not _annual_duration(start, end)):
            continue
        value = _number(_text(node))
        if value is None:
            continue
        tag = ("us-gaap" if "us-gaap" in namespace else "ifrs-full") + ":" + qname.localname
        facts.append(Fact(tag, _row_label(node, tag), unit, value, start, end, filing.accession, filing.filed, filing.form, filing.source_url, statement, "xbrl-instance"))
    return _deduplicate(facts)


def parse_company_facts(payload: dict, filings: list[Filing]) -> list[Fact]:
    """Annual, company-wide standard observations; no guessed custom mappings."""
    filing_map = {filing.accession: filing for filing in filings if filing.form.upper() in ANNUAL_FORMS}
    annual_ends = {filing.report_date for filing in filing_map.values() if _date(filing.report_date)}
    namespaces = payload.get("facts", {})
    for namespace in ("us-gaap", "ifrs-full"):
        for concept in namespaces.get(namespace, {}).values():
            for observations in concept.get("units", {}).values():
                for observation in observations:
                    if observation.get("form", "").upper() in ANNUAL_FORMS and _annual_duration(observation.get("start"), observation.get("end", "")):
                        annual_ends.add(observation["end"])
    facts = []
    for namespace in ("us-gaap", "ifrs-full"):
        for local, concept in namespaces.get(namespace, {}).items():
            statement = _TAG_STATEMENT.get(local)
            if not statement:
                continue
            for unit, observations in concept.get("units", {}).items():
                for observation in observations:
                    form = observation.get("form", "").upper()
                    start, end = observation.get("start"), observation.get("end", "")
                    accession, filed = observation.get("accn", ""), observation.get("filed", "")
                    if form not in ANNUAL_FORMS or not accession or not _date(filed) or not _date(end) or _date(end) > _date(filed):
                        continue
                    if statement == STATEMENTS[1]:
                        if start or end not in annual_ends:
                            continue
                    elif not _annual_duration(start, end):
                        continue
                    try:
                        raw_value = observation["val"]
                        if isinstance(raw_value, bool):
                            continue
                        value = float(raw_value)
                    except (KeyError, TypeError, ValueError, OverflowError):
                        continue
                    if not math.isfinite(value):
                        continue
                    filing = filing_map.get(accession)
                    if filing and not _valid_end(end, filing):
                        continue
                    source = filing.source_url if filing else ""
                    if not source and payload.get("cik"):
                        source = f"https://www.sec.gov/Archives/edgar/data/{int(payload['cik'])}/{accession.replace('-', '')}/{accession}-index.html"
                    facts.append(Fact(f"{namespace}:{local}", concept.get("label") or _row_label(etree.Element("fact"), local), unit, value, start, end, accession, filed, form, source, statement, "companyfacts"))
    return _deduplicate(facts)


_MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): index for index, name in enumerate(calendar.month_abbr) if name})
_MONTH_RE = "(?:" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_FULL_DATE = re.compile(rf"\b({_MONTH_RE})\s+(\d{{1,2}})\s*,?\s*(\d{{4}})\b", re.I)
_MONTH_DAY = re.compile(rf"\b({_MONTH_RE})\s+(\d{{1,2}})\b", re.I)


def _header_date(text: str, default_month_day: tuple[int, int] | None) -> str | None:
    match = _FULL_DATE.search(text)
    try:
        if match:
            month, day, year = match.groups()
            return date(int(year), _MONTHS[month.lower().rstrip(".")], int(day)).isoformat()
        year_match = re.fullmatch(r"\s*\(?((?:19|20)\d{2})\)?\s*", text)
        if year_match and default_month_day:
            return date(int(year_match[1]), *default_month_day).isoformat()
    except ValueError:
        return None
    return None


def _grid_cells(row) -> list:
    cells = []
    for cell in row.xpath("./td|./th"):
        try:
            span = min(30, max(1, int(cell.get("colspan", "1"))))
        except ValueError:
            span = 1
        cells.extend([cell] * span)
    return cells


def _untagged_column_value(cells: list, columns: list[int], scale: str = "0") -> float | None:
    """Read one dated group, including split currency and parenthesis cells.

    A date header may span several physical columns. Combining arbitrary text
    would concatenate adjacent numeric values, so require exactly one numeric
    fragment and allow only empty/currency/sign cells around it.
    """
    if not columns or min(columns) >= len(cells):
        return None
    selected = []
    seen = set()
    for column in columns:
        if column >= len(cells):
            continue
        cell = cells[column]
        if cell not in seen:
            selected.append(cell)
            seen.add(cell)
    tokens = [_text(cell) for cell in selected]
    numerical = [token for token in tokens if re.search(r"\d", token)]
    if len(numerical) != 1 or any(re.search(r"[A-Za-z]", token) for token in tokens):
        return None
    if any(not re.fullmatch(r"[\d\s.,$€£¥()+\-\u2212\u2013\u2014]*", token) for token in tokens):
        return None
    first, last = min(columns), max(columns)
    # Headers sometimes cover only the number, with parentheses outside the
    # colspan. Only attach neighboring symbols; never cross another number.
    for index in range(first - 1, max(-1, first - 5), -1):
        cell = cells[index]
        if cell in seen:
            continue
        text = _text(cell)
        if text and not re.fullmatch(r"[$€£¥(+\-\u2212\s]+", text):
            break
        tokens.insert(0, text)
        seen.add(cell)
    for index in range(last + 1, min(len(cells), last + 5)):
        cell = cells[index]
        if cell in seen:
            continue
        text = _text(cell)
        if text and not re.fullmatch(r"[)\s]+", text):
            break
        tokens.append(text)
        seen.add(cell)
    return _number("".join(tokens), scale=scale)


def _parse_untagged_table(table, statement: str, heading: str, filing: Filing) -> list[Fact]:
    rows = table.xpath("./tr|./thead/tr|./tbody/tr")
    header_text = heading + " " + " ".join(_text(row) for row in rows[:8])
    # Older non-XBRL reports are eligible only when annual period and currency
    # evidence are present. Text filings, image tables, and ambiguous tables remain
    # coverage gaps, rather than fabricated historical values.
    if statement != STATEMENTS[1] and not re.search(r"\byears?\s+ended\b", header_text, re.I):
        return []
    if not ("$" in _text(table) or re.search(r"\b(?:USD|U\.S\.\s*dollars|dollars)\b", header_text, re.I)):
        return []
    if re.search(r"\b(?:Canadian|Australian|Hong\s+Kong)\s+dollars|\b(?:CAD|AUD|HKD|EUR|GBP)\b|(?:CA|AU|HK)\$", header_text, re.I):
        return []
    if filing.form.upper().startswith(("20-F", "40-F")) and not re.search(r"\bUSD\b|\bU\.?S\.?\s*dollars\b|US\$", header_text, re.I):
        return []
    month_days = {(int(_MONTHS[match[1].lower().rstrip(".")]), int(match[2])) for match in _MONTH_DAY.finditer(header_text)}
    default_month_day = next(iter(month_days)) if len(month_days) == 1 else None
    column_dates = {}
    header_index = -1
    for index, row in enumerate(rows[:8]):
        candidates = {column: end for column, cell in enumerate(_grid_cells(row)) if (end := _header_date(_text(cell), default_month_day)) and _valid_end(end, filing)}
        if len(set(candidates.values())) >= 2:
            column_dates, header_index = candidates, index
    if not column_dates:
        return []
    scale = "6" if re.search(r"\bin\s+millions\b", header_text, re.I) else "3" if re.search(r"\bin\s+thousands\b", header_text, re.I) else "0"
    period_columns = defaultdict(list)
    for column, end in column_dates.items():
        period_columns[end].append(column)
    facts = []
    section = unit_section = ""
    for row in rows[header_index + 1:]:
        cells = _grid_cells(row)
        if not cells:
            continue
        label = next((_text(cell).strip(" :") for cell in cells[:min(column_dates)] if re.search(r"[A-Za-z]", _text(cell))), "")
        if not label or len(label) > 250:
            continue
        share_count_heading = _section_heading(label, statement) == "Weighted average shares"
        explicit_per_share = not share_count_heading and bool(re.search(r"per\s+(?:common\s+)?share|earnings\s+per|loss\s+per", label, re.I))
        has_numbers = any(_untagged_column_value(cells, columns) is not None for columns in period_columns.values())
        if not has_numbers:
            found_section = _section_heading(label, statement)
            if found_section:
                section = found_section
            if explicit_per_share:
                unit_section = "per-share"
            elif re.search(r"\b(?:shares?|weighted\s+average)\b", label, re.I):
                unit_section = "shares"
            elif found_section:
                unit_section = ""
            continue
        grouped_eps = unit_section == "per-share" and bool(re.search(r"\b(?:basic|diluted|continuing|discontinued|net\s+income|net\s+loss)\b", label, re.I))
        per_share = explicit_per_share or grouped_eps
        shares = bool(re.search(r"\bshares?\b", label, re.I)) and not per_share
        # Bare share counts have different exceptions/scales across companies.
        # Do not apply a dollar scale to them without explicit evidence.
        if shares or unit_section == "shares" or (re.fullmatch(r"basic|diluted", label, re.I) and not per_share) or re.search(r"percent|percentage|tax\s+rate", label, re.I):
            continue
        unit = "USD/shares" if per_share else "USD"
        row_scale = "0" if per_share else scale
        slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        if not slug:
            continue
        tag = "html:" + re.sub(r"[^a-z]", "", statement.lower()) + ":" + slug
        for end, columns in period_columns.items():
            value = _untagged_column_value(cells, columns, scale=row_scale)
            if value is None:
                continue
            # Full-year text is an explicit condition, not a date invented from a
            # quarter. Start is conventional and disclosed in the extraction note.
            start = None
            if statement != STATEMENTS[1]:
                # Inclusive fiscal year beginning the day after prior year end.
                final = date.fromisoformat(end)
                prior_year = final.year - 1
                prior_end = date(prior_year, final.month, min(final.day, calendar.monthrange(prior_year, final.month)[1]))
                start = (prior_end + timedelta(days=1)).isoformat()
            facts.append(Fact(tag, label, unit, value, start, end, filing.accession, filing.filed, filing.form, filing.source_url, statement, "html-table", "Untagged annual table: year-start convention inferred; period end, label, currency and scale read from table.", presentation_value=value, section=section))
        section = _section_after_total(label, statement, section)
    # Duplicate human labels may refer to different subtotals. Reject contradictory
    # duplicates later; never silently add them together or overwrite one.
    return _deduplicate(facts)


def assemble_bundle(company: Company, filings: list[Filing], facts: list[Fact], coverage: list[CoverageRecord], warnings: list[str]) -> StatementBundle:
    """Align proven equivalent rows without losing source identities or revisions.

    The latest native table supplies the presentation. A newer standardized fact
    can update the same concept, while known missing core lines can be supplied
    by the same or a newer filing. A partial native table must not hide EPS or
    cash-flow totals that the very same filing supplies through companyfacts.
    """
    from .normalization import (clean_label, concept_for, fallback_presentation,
                                include_on_face, row_identity, row_order)

    accepted = [fact for fact in _deduplicate(facts) if fact.statement in STATEMENTS and fact.form.upper() in ANNUAL_FORMS and math.isfinite(fact.value) and _date(fact.end) and (fact.statement == STATEMENTS[1] and fact.start is None or fact.statement != STATEMENTS[1] and _annual_duration(fact.start, fact.end))]
    result = StatementBundle(company=company, filings=filings, raw_facts=accepted, coverage=coverage, warnings=list(warnings))
    source_rank = {"inline-xbrl": 3, "html-table": 2, "xbrl-instance": 1, "companyfacts": 0}
    native_types = {"inline-xbrl", "html-table"}
    by_period = defaultdict(list)
    observations = defaultdict(list)
    for fact in accepted:
        by_period[(fact.statement, fact.end)].append(fact)
        observations[(fact.statement, row_identity(fact), fact.end)].append(fact)

    # If a filing explicitly presents two candidate aliases with different values,
    # their scopes are not proven equivalent for this company. Keep both tags.
    aliases = defaultdict(list)
    for fact in accepted:
        aliases[(fact.statement, fact.end, fact.accession, row_identity(fact), fact.extraction)].append(fact)
    split_aliases = set()
    for (statement, end, accession, identity, extraction), values in aliases.items():
        if len({fact.tag for fact in values}) > 1 and len({fact.presentation_value if fact.presentation_value is not None else fact.value for fact in values}) > 1:
            split_aliases.add((statement, identity))
    if split_aliases:
        result.warnings.append("Some similarly named concepts have different values within a reported statement. Their source tags remain separate instead of merging different scopes.")

    def identity(fact):
        key = row_identity(fact)
        return (fact.tag, key[1], key[2]) if (fact.statement, key) in split_aliases else key

    rows = {statement: {} for statement in STATEMENTS}
    ordering = {}
    fallback_used = False
    untagged_used = False
    mixed_periods = set()
    supplemented_periods = set()
    for (statement, end), all_candidates in sorted(by_period.items(), key=lambda item: item[0][1], reverse=True):
        candidates = [fact for fact in all_candidates if include_on_face(fact)]
        native = [fact for fact in candidates if fact.extraction in native_types]
        latest_native = max(((fact.filed, fact.accession) for fact in native), default=None)
        main_table = [fact for fact in native if (fact.filed, fact.accession) == latest_native]
        baseline_keys = {identity(fact) for fact in main_table}
        selected_candidates = list(main_table)
        if main_table:
            for fact in candidates:
                if fact.extraction in native_types or (fact.filed, fact.accession) < latest_native:
                    continue
                concept = concept_for(fact)
                key = identity(fact)
                # No arbitrary supplemental note concepts. Balance-sheet amounts
                # with an explicit curated face identity can fill a partial table.
                same_filing_cash_detail = statement == STATEMENTS[2] and (fact.filed, fact.accession) == latest_native
                supplements = concept and (concept.supplement or statement == STATEMENTS[1] or same_filing_cash_detail)
                if key in baseline_keys or supplements:
                    selected_candidates.append(fact)
        else:
            selected_candidates = [fact for fact in candidates if fact.extraction not in native_types]
        grouped = defaultdict(list)
        for fact in selected_candidates:
            grouped[identity(fact)].append(fact)
        for key, values in grouped.items():
            latest = max((fact.filed, fact.accession) for fact in values)
            winners = [fact for fact in values if (fact.filed, fact.accession) == latest]
            best_rank = max(source_rank.get(fact.extraction, 0) for fact in winners)
            best = [fact for fact in winners if source_rank.get(fact.extraction, 0) == best_rank]
            # Native HTML annual starts are conventional; they must not conflict
            # with a more precise XBRL context from the same reported table.
            unique = {(fact.value, fact.start, fact.presentation_value) for fact in best}
            recovered_conflict = False
            if len(unique) != 1:
                # A malformed untagged table can mislabel a share count as EPS.
                # Recover only from unanimous independently standardized facts
                # for the same known identity, unit, annual period and filing.
                standardized = [fact for fact in winners if fact.extraction in {"companyfacts", "xbrl-instance"} and concept_for(fact)]
                standard_values = {(fact.value, fact.start, fact.presentation_value) for fact in standardized}
                if all(fact.extraction == "html-table" for fact in best) and standardized and len(standard_values) == 1:
                    best = sorted(standardized, key=lambda fact: source_rank.get(fact.extraction, 0), reverse=True)
                    recovered_conflict = True
                    result.warnings.append(f"Ambiguous HTML {key[0]} ({key[1]}) for {end} in {latest[1]}: used the consistent standardized fact from that same filing; conflicting HTML observations remain in source records.")
                else:
                    result.warnings.append(f"Ambiguous {key[0]} ({key[1]}) for {end} in {latest[1]}: conflicting consolidated observations were left blank.")
                    continue
            picked = best[0]
            prior = [fact for fact in observations[(statement, row_identity(picked), end)] if (fact.filed, fact.accession) < latest]
            if picked.start and any(fact.start and abs((_date(fact.start) - _date(picked.start)).days) > 14 for fact in prior):
                result.warnings.append(f"{picked.label} ({picked.tag}), {end}: earlier observations cover different annual start dates; the latest period was selected and is not directly comparable.")
            # Compare the same source concept's sign; HTML cash outflows are
            # printed negative while corresponding XBRL payment values are debit
            # positive. Presentation comparison avoids a false revision warning.
            display = fallback_presentation(picked)
            display = picked.value if display is None else display
            changed = any(not math.isclose(fact.value if fallback_presentation(fact) is None else fallback_presentation(fact), display, rel_tol=1e-10, abs_tol=1e-9) for fact in prior)
            is_fallback = picked.extraction not in native_types
            fallback_used |= is_fallback
            supplement = bool(main_table and key not in baseline_keys and is_fallback)
            if supplement:
                supplemented_periods.add((statement, end))
                reason = "Core statement line missing from extracted primary table; filled from a standardized fact in the same or a later annual filing."
            elif is_fallback:
                reason = "Latest available annual filing observation for this concept and period."
            else:
                reason = "Latest available main-statement observation for this period."
            if main_table and latest != latest_native:
                mixed_periods.add((statement, end))
                reason += " This concept is from a later filing than the retained native statement layout; check statement reconciliation."
            if changed:
                reason += " Value differs from an earlier filing; may reflect a restatement or reclassification."
                result.warnings.append(f"{clean_label(picked.label)} ({picked.tag}), {end}: the selected later filing changes an earlier observation; see source records.")
            if recovered_conflict:
                reason += " Conflicting HTML observations were excluded; a consistent standardized fact from the same filing supplies this value."
            if picked.selection_reason:
                reason += " " + picked.selection_reason
            presentation = fallback_presentation(picked)
            if presentation is not None and picked.presentation_value is None:
                reason += " Cash-flow presentation uses the defined contribution sign of this standard concept; the original source value is retained."
            concept = concept_for(picked)
            picked = replace(picked, selection_reason=reason, presentation_value=presentation,
                             section=concept.section if concept else picked.section)
            untagged_used |= picked.extraction == "html-table"
            if picked.start:
                duration = (_date(picked.end) - _date(picked.start)).days + 1
                if duration < 340 or duration > 380:
                    result.warnings.append(f"{picked.end}: selected annual period spans {duration} days; review for a transition fiscal year before comparing or forecasting.")
            statement_row = rows[statement].get(key)
            if statement_row is None:
                label = concept.label if concept else clean_label(picked.label)
                if (statement, row_identity(picked)) in split_aliases:
                    label += " [" + picked.tag.rsplit(":", 1)[-1] + "]"
                statement_row = StatementRow(picked.tag, label, picked.unit,
                                             accepted_tags={picked.tag}, section=picked.section,
                                             is_total=bool(concept and concept.is_total))
                rows[statement][key] = statement_row
                ordering[(statement, key)] = row_order(picked)
            statement_row.accepted_tags.add(picked.tag)
            statement_row.values[end] = picked
    result.statements = {statement: [row for key, row in sorted(rows[statement].items(), key=lambda pair: ordering[(statement, pair[0])])] for statement in STATEMENTS}
    result.periods = sorted({end for statement in result.statements.values() for row in statement for end in row.values} | {filing.report_date for filing in filings if filing.form.upper() in ANNUAL_FORMS and _date(filing.report_date)}, reverse=True)
    if fallback_used:
        result.warnings.append("Some periods use SEC companyfacts/standard XBRL fallback. Only explicit equivalent row identities are aligned; source tags and units remain in each cell's source record. Other concepts must not be summed blindly.")
    if supplemented_periods:
        result.warnings.append(f"Standardized source facts fill missing core lines in {len(supplemented_periods)} statement/year combinations; each filled cell identifies this fallback.")
    for statement, end in sorted(mixed_periods):
        result.warnings.append(f"{statement}, {end}: latest values come from multiple filings. Older reported rows are retained where no later equivalent is available; check reconciliation and source dates before modeling.")
    if untagged_used:
        result.warnings.append("Some older periods were extracted from untagged HTML tables. Period start dates use the stated full-year convention; compare every figure and unit against the linked filing before modeling.")
    if any(filing.form.upper() in {"10-KT", "10-KT/A"} for filing in filings):
        result.warnings.append("Transition filings are present. Periods outside 300–400 days were excluded; review remaining fiscal-year changes before comparison.")
    if any(fact.extraction == "inline-xbrl" and fact.statement == STATEMENTS[2] for fact in accepted):
        result.warnings.append("Cash-flow beginning/ending cash balances are included only when their original instant dates match a unique annual statement column. Ambiguous instant rows are omitted; review the linked filing's reconciliation.")
    known_accessions = {filing.accession for filing in filings}
    if any(fact.extraction == "companyfacts" and fact.accession not in known_accessions for fact in accepted):
        result.warnings.append("Some annual SEC companyfacts observations refer to filings absent from the discovered submissions inventory; their filing-index links remain in the source records.")
    result.warnings = list(dict.fromkeys(result.warnings))
    return result
