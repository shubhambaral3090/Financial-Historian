from dataclasses import replace
from financial_historian.models import Company, Fact, Filing, CoverageRecord, StatementBundle
from financial_historian.extract import assemble_bundle
from financial_historian.service import limit_statement_history
from financial_historian.disclosures import parse_disclosures, parse_company_disclosures

SOURCE="https://www.sec.gov/Archives/edgar/data/104169/000010416916000055/annual.htm"


def test_wmt_export_revenue_scopes_keep_total_and_net_sales_without_custom_duplicates():
    # Amounts reproduced from the user's 2016 export; regression evidence, not
    # an independent live source verification or certification of that export.
    facts=[]
    for tag,label,value in [
        ("us-gaap:Revenues","Total revenues",482130),
        ("wmt:total_revenues","Total revenues",482130),
        ("us-gaap:SalesRevenueNet","Net sales",478614),
        ("wmt:net_sales","Net sales",478614),
    ]:
        facts.append(Fact(tag,label,"USD",value*1000000,"2015-02-01","2016-01-31",
                          "0000104169-16-000055","2016-03-30","10-K",SOURCE,"Profit & Loss","inline-xbrl"))
    bundle=assemble_bundle(Company("0000104169","Walmart","WMT","5331"),[],facts,[],[])
    rows=bundle.statements["Profit & Loss"]
    assert len(rows)==2
    assert {r.label for r in rows}=={"Revenue","Net sales"}
    assert {next(iter(r.values.values())).value for r in rows}=={482130000000,478614000000}
    assert len(bundle.raw_facts)==4


def test_wmt_empty_april_metadata_date_does_not_displace_january_annual_history():
    f=Fact("us-gaap:Revenues","Revenue","USD",1,"2008-02-01","2009-01-31","a","2010-03-01","10-K",SOURCE,"Profit & Loss")
    records=[replace(f,start=f"{y-1}-02-01",end=f"{y}-01-31") for y in range(2006,2027)]
    filings=[Filing("odd","10-K","2009-04-01","2009-04-01","annual.htm",SOURCE)]
    coverage=[CoverageRecord("odd","2009-04-01","2009-04-01",SOURCE,"unsupported","No trustworthy annual values")]
    result=limit_statement_history(assemble_bundle(Company("1","Fixture"),filings,records,coverage,[]))
    assert len(result.periods)==20
    assert "2009-04-01" not in result.periods
    assert "2007-01-31" in result.periods
    assert any("Heuristic exclusion" in w for w in result.warnings)
    assert result.coverage==coverage


def test_dimensional_segment_disclosure_keeps_member_and_precision():
    body=b'''<html><body><xbrli:context id="seg"><xbrli:entity><xbrli:segment>
      <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">demo:RetailMember</xbrldi:explicitMember>
      </xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
      <table><tr><td>Retail revenue</td><td><ix:nonFraction name="us-gaap:Revenues" contextRef="seg" unitRef="usd" decimals="-6" scale="6">100</ix:nonFraction></td></tr></table>
      </body></html>'''
    filing=Filing("a","10-K","2025-02-01","2024-12-31","annual.htm",SOURCE)
    facts=parse_disclosures(body,filing)
    assert len(facts)==1
    fact=facts[0]
    assert fact.value==100000000
    assert fact.dimensions==(("us-gaap:StatementBusinessSegmentsAxis","demo:RetailMember"),)
    assert fact.decimals=="-6" and fact.context_id=="seg"
    assert fact.statement=="Disclosure"
    assert not assemble_bundle(Company("1","Fixture"),[filing],facts,[],[]).statements["Profit & Loss"]


def test_unknown_or_quarterly_note_never_becomes_an_annual_schedule():
    source=b'<html><p>Unknown disclosure 42</p></html>'
    assert parse_disclosures(source,Filing("a","10-Q","2025-02-01","2024-12-31","x",SOURCE))==[]


def test_raw_records_keep_context_precision_and_dimensions():
    f=Fact("us-gaap:Revenues","Revenue","USD",100,"2024-01-01","2024-12-31","a","2025-02-01","10-K",SOURCE,"Profit & Loss",context_id="one",decimals="0")
    from financial_historian.extract import _deduplicate
    records=[f,replace(f,context_id="two"),replace(f,decimals="-3"),replace(f,dimensions=(("demo:RegionAxis","demo:USMember"),)),f]
    assert len(_deduplicate(records))==4


def test_companyfacts_curated_notes_reject_quarters_and_unknown_concepts():
    filing=Filing("a","10-K","2025-02-01","2024-12-31","annual.htm",SOURCE)
    obs={"accn":"a","form":"10-K","filed":"2025-02-01","start":"2024-01-01","end":"2024-12-31","val":12}
    payload={"facts":{"us-gaap":{
        "InterestExpense":{"label":"Interest expense","units":{"USD":[obs,dict(obs,start="2024-10-01"),dict(obs,form="10-Q")] }},
        "UnmappedConcept":{"units":{"USD":[obs]}}}}}
    facts=parse_company_disclosures(payload,[filing])
    assert len(facts)==1
    assert facts[0].value==12 and facts[0].tag=="us-gaap:InterestExpense"
    assert not facts[0].context_id and not facts[0].decimals
