from dataclasses import replace

from financial_historian.models import Company, Fact, STATEMENTS, StatementBundle, StatementRow
from financial_historian.quality import inspect_bundle, inspect_filing


def fact(tag, value, statement, *, unit="USD", accession="0000000001-24-000001"):
    return Fact("us-gaap:" + tag, tag, unit, value,
                None if statement == STATEMENTS[1] else "2023-01-01",
                "2023-12-31", accession, "2024-02-01", "10-K",
                "https://www.sec.gov/Archives/edgar/data/1/annual.htm", statement,
                "inline-xbrl", presentation_value=value)


def complete_facts():
    return [
        fact("SalesRevenueNet", 500, STATEMENTS[0]),
        fact("NetIncomeLoss", 80, STATEMENTS[0]),
        fact("Assets", 1000, STATEMENTS[1]),
        fact("Liabilities", 600, STATEMENTS[1]),
        fact("StockholdersEquity", 400, STATEMENTS[1]),
        fact("NetCashProvidedByUsedInOperatingActivities", 120, STATEMENTS[2]),
        fact("NetCashProvidedByUsedInInvestingActivities", -50, STATEMENTS[2]),
        fact("NetCashProvidedByUsedInFinancingActivities", -60, STATEMENTS[2]),
        fact("CashAndCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect", 10, STATEMENTS[2]),
        fact("EffectOfExchangeRateOnCashAndCashEquivalents", 0, STATEMENTS[2]),
    ]


def test_one_fact_per_statement_cannot_establish_complete_extraction():
    result = inspect_filing([fact("Unknown", 1, statement) for statement in STATEMENTS], "2023-12-31")
    assert any("Core rows not verified" in message for message in result)
    assert "investing cash flow" in result[0]


def test_matching_reported_totals_pass_and_wrong_balance_is_flagged():
    facts = complete_facts()
    assert inspect_filing(facts, "2023-12-31") == []
    facts[2] = replace(facts[2], value=1100, presentation_value=1100)
    assert any("Assets versus liabilities plus equity does not reconcile" in message
               for message in inspect_filing(facts, "2023-12-31"))


def test_missing_cash_flow_totals_remain_missing_despite_positive_other_rows():
    facts = [f for f in complete_facts() if "InvestingActivities" not in f.tag]
    result = inspect_filing(facts, "2023-12-31")
    assert any("investing cash flow" in message for message in result)


def test_cash_flow_total_reconciliation_uses_reported_exchange_effect():
    facts = complete_facts()
    facts[-2] = replace(facts[-2], value=999, presentation_value=999)
    assert any("Operating/investing/financing cash flows" in message
               for message in inspect_filing(facts, "2023-12-31"))
    assert not any("does not reconcile" in message
                   for message in inspect_filing(facts[:-1], "2023-12-31"))


def test_reconciliation_never_mixes_currencies_or_filing_accessions():
    facts = complete_facts()
    facts[2] = replace(facts[2], value=9000, presentation_value=9000, unit="EUR")
    assert not any("does not reconcile" in message for message in inspect_filing(facts, "2023-12-31"))
    facts[2] = replace(facts[2], unit="USD", accession="0000000001-25-000001")
    assert not any("does not reconcile" in message for message in inspect_filing(facts, "2023-12-31"))


def test_prior_comparatives_do_not_make_empty_report_year_complete():
    assert "Core rows not verified" in inspect_filing(complete_facts(), "2024-12-31")[0]


def test_parent_equity_not_added_to_consolidated_liabilities_when_nci_present():
    facts = complete_facts()
    facts[2] = replace(facts[2], value=1100, presentation_value=1100)
    facts.append(fact("MinorityInterest", 100, STATEMENTS[1]))
    assert not any("does not reconcile" in message for message in inspect_filing(facts, "2023-12-31"))


def test_selected_history_flags_mixed_filing_reconciliation_failure():
    bundle = StatementBundle(Company("1", "Example"))
    for f in complete_facts():
        if f.tag.endswith(":StockholdersEquity"):
            f = replace(f, value=399, presentation_value=399, accession="0000000001-25-000001")
        bundle.statements[f.statement].append(StatementRow(f.tag, f.label, f.unit, {f.end: f}))
    issues = inspect_bundle(bundle)
    # Difference is exactly one unscaled unit, within published rounding tolerance.
    assert not any("different filings" in issue for issue in issues)
    equity = next(row for row in bundle.statements[STATEMENTS[1]] if row.tag.endswith(":StockholdersEquity"))
    equity.values["2023-12-31"] = replace(equity.values["2023-12-31"], value=350, presentation_value=350)
    assert any("Selected values from different filings" in issue and "does not reconcile" in issue
               for issue in inspect_bundle(bundle))
