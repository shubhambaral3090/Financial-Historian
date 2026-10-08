from dataclasses import replace
from pathlib import Path

from financial_historian.parsed_cache import ParsedFilingCache
from financial_historian.models import Filing
from test_analysis import historical_fixture
from test_research import COMPANY, Clock, FixtureService, FixtureMarket, exporter
from financial_historian.research import ResearchController


def test_parsed_cache_roundtrip_expiry_size_and_parser_inputs(tmp_path):
    now=[100000.0]
    cache=ParsedFilingCache(tmp_path,max_bytes=10000,ttl_seconds=10,clock=lambda:now[0])
    f=historical_fixture().raw_facts[0]
    filing=Filing(f.accession,f.form,f.filed,f.end,"annual.htm",f.source_url)
    key=cache.key(b"document",filing)
    cache.put(key,[f],[replace(f,statement="Disclosure",dimensions=(("demo:Axis","demo:Member"),))])
    facts,notes=cache.get(key)
    assert facts==[f] and notes[0].dimensions==(("demo:Axis","demo:Member"),)
    assert cache.key(b"changed",filing)!=key
    assert cache.key(b"document",replace(filing,report_date="2020-12-31"))!=key
    now[0]+=11
    assert cache.get(key) is None
    cache.put("second",[f],[])
    assert not (tmp_path/(key+".json")).exists()
    limited=ParsedFilingCache(tmp_path/"tiny",max_bytes=1)
    limited.put(key,[f],[])
    assert limited.get(key) is None


def test_corrupt_parse_cache_is_a_miss_and_never_executes(tmp_path):
    cache=ParsedFilingCache(tmp_path)
    for content in ('not json','{}','[[],[{"unknown":42}]]'):
        (tmp_path/"bad.json").write_text(content)
        assert cache.get("bad") is None


def test_navigation_reuses_recent_bundle_but_expiry_and_reload_recheck():
    clock=Clock()
    controller=ResearchController(clock=clock,exporter=exporter,freshness_seconds=10)
    service,market=FixtureService(),FixtureMarket()
    one=controller.load(service,COMPANY,market,force_refresh=False)
    two=controller.load(service,COMPANY,market,force_refresh=False)
    assert len(service.retrievals)==1
    assert two.sec_retrieved_at==one.sec_retrieved_at and two.analysis is not None
    controller.load(service,COMPANY,market,force_refresh=True)
    assert len(service.retrievals)==2
    clock.advance(11)
    controller.load(service,COMPANY,market,force_refresh=False)
    assert len(service.retrievals)==3


def test_statements_arrive_before_export_and_stage_diagnostics_are_safe():
    events=[]
    def blocked_export(bundle,progress=None):
        # Delivery happens on the UI thread; test event order after completion.
        return b"workbook"
    service,market=FixtureService(),FixtureMarket()
    result=ResearchController(exporter=blocked_export).load(service,COMPANY,market,on_event=events.append)
    kinds=[e.kind for e in events]
    assert kinds.index("financial")<kinds.index("workbook")
    assert result.analysis is next(e.analysis for e in events if e.kind=="workbook")
    timings={e.message:e.duration_seconds for e in events if e.kind=="timing"}
    assert {"company_profile","sec_retrieval_and_parsing","analysis","excel","market"}<=timings.keys()
    assert all(value>=0 for value in timings.values())
    service.fail_finances=True
    events.clear()
    ResearchController().load(service,COMPANY,market,on_event=events.append)
    diagnostics=[e.message for e in events if e.kind=="diagnostic"]
    assert diagnostics==["sec:RuntimeError"]
