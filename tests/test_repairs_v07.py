"""Regression amounts from the supplied v0.6 exports, not a live SEC audit."""
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

from financial_historian.analysis import Calculator, build_analysis, source_datum
from financial_historian.compatibility import reconcile_html_periods
from financial_historian.extended_metrics import same_filing_prior
from financial_historian.extract import assemble_bundle
from financial_historian.models import Company, Fact, Filing, CoverageRecord, StatementBundle
from financial_historian.service import limit_statement_history
from test_analysis import historical_fixture, cell, mutate


def apple(tag, value, start="2015-09-27", **kw):
    return Fact(tag,kw.pop("label",tag),"USD",value,start,"2016-09-24",
                "0000320193-18-000145","2018-11-05","10-K",
                "https://www.sec.gov/Archives/edgar/data/320193/000032019318000145/a10-k20189292018.htm",
                "Profit & Loss",**kw)


def test_apple_2016_same_filing_revenue_start_and_margin():
    facts=[apple("us-gaap:Revenues",215639000000),
           apple("html:profitloss:net_sales",215639000000,"2015-09-25",label="Net sales",extraction="html-table",presentation_value=215639000000),
           apple("html:profitloss:operating_income",60024000000,"2015-09-25",label="Operating income",extraction="html-table",presentation_value=60024000000)]
    bundle=assemble_bundle(Company("0000320193","Apple Inc.","AAPL","3571"),[],facts,[],[])
    assert len(bundle.statements["Profit & Loss"])==2
    revenue=bundle.statements["Profit & Loss"][0].values["2016-09-24"]
    assert revenue.start=="2015-09-27"
    assert "Original HTML convention: 2015-09-25" in revenue.selection_reason
    assert facts[1] in bundle.raw_facts and facts[1].start=="2015-09-25"
    metric=Calculator(bundle).metric("operating_margin","2016-09-24")
    assert float(metric.value)==pytest.approx(60024/215639)


@pytest.mark.parametrize("other_start",["2015-09-26","2015-10-03"])
def test_ambiguous_structured_start_does_not_repair_html(other_start):
    html=apple("html:profitloss:net_sales",100,"2015-09-25",extraction="html-table")
    result=reconcile_html_periods([html,apple("us-gaap:Revenues",100),apple("us-gaap:OperatingIncomeLoss",10,other_start)])
    assert result[0] is html


@pytest.mark.parametrize("current,prior,expected",[(7.46,6.08,7.46/6.08-1),(3.33,2.55,3.33/2.55-1)])
def test_export_eps_duplicates_have_identical_effective_values(current,prior,expected):
    now=replace(apple("us-gaap:EarningsPerShareDiluted",current),unit="USD/shares",start="2024-09-29",end="2025-09-27")
    old=replace(now,value=prior,start="2023-10-01",end="2024-09-28")
    inline=replace(old,extraction="inline-xbrl",presentation_value=prior,context_id="annual")
    engine=SimpleNamespace(selected=[now],bundle=SimpleNamespace(raw_facts=[old,inline],disclosures=[replace(old,statement="Disclosure")]))
    result=same_filing_prior(engine,source_datum(now),old.end)
    assert float(source_datum(now).value/result.value-1)==pytest.approx(expected)
    engine.bundle.raw_facts.append(replace(inline,presentation_value=-prior))
    assert same_filing_prior(engine,source_datum(now),old.end).value is None


def test_unchanged_vintage_can_be_verified_without_changing_statement():
    bundle=historical_fixture()
    mutate(bundle,"LiabilitiesCurrent",accession="later")
    selected=next(r for r in bundle.statements["Balance Sheet"] if r.tag.endswith(":LiabilitiesCurrent"))
    result=cell(build_analysis(bundle),"current_ratio")
    assert result.value==Decimal("2.5")
    assert selected.values["2024-12-31"].accession=="later"
    assert len({f.accession for f in result.sources})==1
    assert any("Unchanged amount verified" in f.selection_reason for f in result.sources)
    mutate(bundle,"LiabilitiesCurrent",value=170000000)
    assert cell(build_analysis(bundle),"current_ratio").value is None


def test_apple_current_marketable_securities_can_supply_quick_ratio():
    bundle=historical_fixture()
    row=next(r for r in bundle.statements["Balance Sheet"] if r.tag.endswith(":ShortTermInvestments"))
    row.tag="us-gaap:MarketableSecuritiesCurrent"
    row.values={p:replace(f,tag=row.tag) for p,f in row.values.items()}
    result=cell(build_analysis(bundle),"quick_ratio")
    assert result.value==Decimal(190)/160
    assert any(f.tag==row.tag for f in result.sources)


def test_cisco_interest_source_amount_is_not_negative_printed_contribution():
    bundle=historical_fixture()
    row=next(r for r in bundle.statements["Profit & Loss"] if r.tag.endswith(":InterestExpense"))
    row.tag="us-gaap:InterestExpenseNonoperating"
    row.values={p:replace(f,tag=row.tag,presentation_value=-f.value) for p,f in row.values.items()}
    assert cell(build_analysis(bundle),"interest_coverage").value==15
    assert row.values["2024-12-31"].presentation_value==-12000000


def test_interest_income_does_not_merge_with_interest_and_dividend_income():
    interest=apple("us-gaap:InvestmentIncomeInterest",100,label="Interest income")
    combined=replace(interest,tag="us-gaap:InvestmentIncomeInterestAndDividend",
                     label="Interest and dividend income",end="2017-09-30",start="2016-09-25")
    bundle=assemble_bundle(Company("1","Scope fixture"),[],[interest,combined],[],[])
    rows=bundle.statements["Profit & Loss"]
    assert len(rows)==2
    assert {row.label for row in rows}=={"Interest income","Interest and dividend income"}
    assert all(len(row.values)==1 for row in rows)


def test_tax_rate_does_not_need_alternative_income_tag():
    bundle=historical_fixture()
    bundle.statements["Profit & Loss"]=[r for r in bundle.statements["Profit & Loss"] if not r.tag.endswith(":ProfitLoss")]
    template=bundle.statements["Profit & Loss"][0].values["2024-12-31"]
    bundle.disclosures=[replace(template,tag="us-gaap:IncomeTaxExpenseBenefit",value=29749000000,statement="Disclosure"),
                        replace(template,tag="us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",value=123485000000,statement="Disclosure")]
    result=build_analysis(bundle)
    assert float(cell(result,"effective_tax").value)==pytest.approx(29749/123485)
    assert cell(result,"roa").value is None  # Parent is not silently consolidated.
    assert float(cell(result,"roa_parent").value)==pytest.approx(118/1200)


def test_cisco_receivables_allowance_label_does_not_duplicate_row():
    a=replace(apple("us-gaap:AccountsReceivableNetCurrent",5554000000),statement="Balance Sheet",start=None,end="2018-07-28")
    b=replace(a,tag="html:balancesheet:accounts_receivable_net_of_allowance_for_doubtful_accounts",extraction="html-table",label="Accounts receivable, net of allowance for doubtful accounts of $136 at July 27, 2019 and $129 at July 28, 2018")
    bundle=assemble_bundle(Company("858877","Cisco"),[],[a,b],[],[])
    assert len(bundle.statements["Balance Sheet"])==1
    assert len(bundle.raw_facts)==2


def test_short_transition_period_is_not_hidden_by_nearby_annual_date():
    bundle=historical_fixture()
    source=bundle.raw_facts[0].source_url
    bundle.filings=[Filing("transition","10-KT","2025-04-01","2025-03-01","annual.htm",source)]
    bundle.coverage=[CoverageRecord("transition","2025-03-01","2025-04-01",source,"unsupported","Short transition")]
    assert "2025-03-01" in limit_statement_history(bundle).periods


def test_filing_day_metadata_exclusion_requires_same_accession_evidence():
    bundle=historical_fixture()
    f=bundle.raw_facts[-1]
    bundle.filings=[Filing(f.accession,"10-K",f.filed,f.filed,"annual.htm",f.source_url)]
    bundle.coverage=[CoverageRecord(f.accession,f.filed,f.filed,f.source_url,"unsupported","Invalid metadata")]
    assert f.filed not in limit_statement_history(bundle).periods


@pytest.mark.parametrize("label",["Cash and restricted cash, end of fiscal year", "Cash and restricted cash at fiscal year-end"])
def test_cash_ending_fiscal_year_label_preserves_real_instant(label):
    from test_extract import document, table, row, tagged, FILING
    from financial_historian.extract import parse_filing_html
    content=table("Consolidated Statements of Cash Flows",
                  row("Operating cash flow",tagged("20",tag="us-gaap:NetCashProvidedByUsedInOperatingActivities"))+
                  row(label,tagged("100",context="instant",tag="us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")))
    facts=parse_filing_html(document(content),FILING)
    ending=next(f for f in facts if f.row_role=="cash_end")
    assert ending.source_instant=="2023-12-31" and ending.value==100


@pytest.mark.parametrize("start,end,days",[("2022-09-25","2023-09-30",371),("2023-10-01","2024-09-28",364)])
def test_52_53_week_days_follow_actual_contexts(start,end,days):
    f=replace(apple("us-gaap:Revenues",100),start=start,end=end)
    bundle=assemble_bundle(Company("1","Weekly fixture","WEEK","3571"),[],[f],[],[])
    assert Calculator(bundle).days(end).value==days


def test_split_boundary_uses_documented_common_filing_pair_and_flags_display():
    from financial_historian.models import StatementRow
    from financial_historian.extended_metrics import same_filing_pair
    current=replace(apple("us-gaap:EarningsPerShareDiluted",6.31),unit="USD/shares",start="2011-09-25",end="2012-09-29",accession="2014",filed="2014-10-27")
    original=replace(current,value=44.15,accession="2013",filed="2013-10-30")
    previous=replace(original,value=27.68,start="2010-09-26",end="2011-09-24")
    row=StatementRow(current.tag,"Diluted EPS",current.unit,{current.end:current,previous.end:previous})
    bundle=StatementBundle(Company("320193","Apple","AAPL","3571"),periods=[previous.end,current.end],raw_facts=[current,original,previous])
    bundle.statements["Profit & Loss"]=[row]
    engine=Calculator(bundle)
    a,b=same_filing_pair(engine,source_datum(current),previous.end)
    assert a.value==Decimal("44.15") and b.value==Decimal("27.68")
    result=build_analysis(bundle)
    assert len(result.basis_reviews)==1
    assert result.basis_reviews[0]["Selected current value"]==6.31
    assert float(cell(result,"diluted_eps_growth",current.end).value)==pytest.approx(44.15/27.68-1)
