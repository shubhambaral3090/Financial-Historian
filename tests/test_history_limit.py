import pytest

from financial_historian.models import Company, Fact, Filing, StatementBundle, StatementRow
from financial_historian.service import limit_statement_history


def test_history_limit_keeps_latest_periods_but_retains_raw_facts():
    bundle = StatementBundle(Company("1", "Example"))
    facts = []
    for year in range(2000, 2026):
        end = f"{year}-12-31"
        fact = Fact("us-gaap:Revenues", "Revenue", "USD", year, f"{year}-01-01", end, "0000000001-26-000001", "2027-01-01", "10-K", "https://www.sec.gov/Archives/edgar/data/1/a.htm", "Profit & Loss")
        facts.append(fact)
    bundle.raw_facts = facts
    bundle.statements["Profit & Loss"] = [StatementRow(facts[0].tag, facts[0].label, facts[0].unit, {fact.end: fact for fact in facts})]
    original = bundle
    bundle = limit_statement_history(bundle, 20)
    assert len(bundle.periods) == 20
    assert bundle.periods[0] == "2025-12-31"
    assert bundle.periods[-1] == "2006-12-31"
    assert len(bundle.raw_facts) == 26
    assert any("latest 20" in warning for warning in bundle.warnings)
    assert len(original.statements["Profit & Loss"][0].values) == 26
    assert original.warnings == []
    assert original.periods == []
    assert limit_statement_history(bundle, 20) == bundle


def test_blank_latest_period_stays_visible_with_coverage_reason():
    bundle = StatementBundle(Company("1", "Example"), filings=[
        Filing("0000000001-26-000001", "10-K", "2026-02-01", "2025-12-31", "annual.htm",
               "https://www.sec.gov/Archives/edgar/data/1/annual.htm")])
    limited = limit_statement_history(bundle)
    assert limited.periods == ["2025-12-31"]
    assert any("2025-12-31; blank columns are intentional" in warning for warning in limited.warnings)


@pytest.mark.parametrize("limit", [True, False, 0, -1, 2.5, "20"])
def test_invalid_period_limits_are_rejected(limit):
    with pytest.raises(ValueError, match="positive integer"):
        limit_statement_history(StatementBundle(Company("1", "Example")), limit)
