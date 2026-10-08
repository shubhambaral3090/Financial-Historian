from financial_historian.models import Company, Fact, StatementBundle, StatementRow
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
    limit_statement_history(bundle, 20)
    assert len(bundle.periods) == 20
    assert bundle.periods[0] == "2025-12-31"
    assert bundle.periods[-1] == "2006-12-31"
    assert len(bundle.raw_facts) == 26
    assert any("latest 20" in warning for warning in bundle.warnings)
