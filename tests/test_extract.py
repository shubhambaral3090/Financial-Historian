"""Extraction regressions focus on period, statement scope, units and provenance."""
from dataclasses import replace

import pytest

from financial_historian.extract import assemble_bundle, parse_company_facts, parse_filing_html, parse_xbrl_instance
from financial_historian.models import Company, Fact, Filing, STATEMENTS


FILING = Filing("0000123456-24-000001", "10-K", "2024-02-15", "2023-12-31", "report.htm", "https://www.sec.gov/report.htm")
COMPANY = Company("123456", "Example Company", "EX")


def document(body: str, extra_contexts: str = "") -> bytes:
    return f"""<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">
    <body><ix:header><ix:resources>
    <xbrli:context id="annual"><xbrli:entity><xbrli:identifier>123456</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2023-01-01</xbrli:startDate><xbrli:endDate>2023-12-31</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:context id="prior"><xbrli:period><xbrli:startDate>2022-01-01</xbrli:startDate><xbrli:endDate>2022-12-31</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:context id="quarter"><xbrli:period><xbrli:startDate>2023-10-01</xbrli:startDate><xbrli:endDate>2023-12-31</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:context id="dimension"><xbrli:entity><xbrli:segment><xbrldi:explicitMember dimension="ex:SegmentsAxis">ex:NorthAmericaMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2023-01-01</xbrli:startDate><xbrli:endDate>2023-12-31</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:context id="instant"><xbrli:period><xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>
    <xbrli:context id="quarterinstant"><xbrli:period><xbrli:instant>2023-09-30</xbrli:instant></xbrli:period></xbrli:context>
    {extra_contexts}
    <xbrli:unit id="dollars"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
    <xbrli:unit id="eps"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
    </ix:resources></ix:header>{body}</body></html>""".encode()


def tagged(value="120", tag="ex:SpecialRevenue", context="annual", attributes="", unit="dollars"):
    default_format = '' if 'format=' in attributes else 'format="ixt:num-dot-decimal"'
    return f'<ix:nonFraction name="{tag}" contextRef="{context}" unitRef="{unit}" {default_format} {attributes}>{value}</ix:nonFraction>'


def table(title, rows):
    return f"<h2>{title}</h2><table>{rows}</table>"


def row(label, value):
    return f"<tr><td>{label}</td><td>{value}</td></tr>"


def fact(value=100.0, *, filing=FILING, extraction="inline-xbrl", tag="us-gaap:Revenues", statement=STATEMENTS[0], start="2023-01-01", end="2023-12-31"):
    return Fact(tag, "Revenue", "USD", value, start, end, filing.accession, filing.filed, filing.form, filing.source_url, statement, extraction)


def test_inline_annual_consolidated_custom_label_scale_and_scope():
    main = table("Consolidated Statements of Income", "".join([
        row("Subscription and specialized services", tagged("1,234.5", attributes='scale="6"')),
        row("Quarter revenue", tagged("400", context="quarter", tag="ex:Quarter")),
        row("Segment revenue", tagged("900", context="dimension", tag="ex:Segment")),
        row("Nil data", tagged("", tag="ex:Missing", attributes='xsi:nil="true"')),
        row("Bad data", tagged("NaN", tag="ex:Bad")),
    ]))
    notes = table("Note 9. Revenue", row("Supplemental revenue", tagged("800", tag="ex:NoteOnly")))
    result = parse_filing_html(document(main + notes), FILING)
    assert len(result) == 1
    found = result[0]
    assert found.tag == "ex:SpecialRevenue"
    assert found.label == "Subscription and specialized services"
    assert found.value == 1_234_500_000
    assert found.statement == "Profit & Loss"
    assert found.extraction == "inline-xbrl"


def test_inline_sign_keeps_tagged_value_separate_from_printed_cash_outflow():
    body = table("Consolidated Statements of Cash Flows", "".join([
        row("Purchases of equipment", f'<span>(</span>{tagged("12,715", tag="us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", attributes="scale=\"6\"")}<span>)</span>'),
        # Some publishers put the closing parenthesis in a separate cell.
        f'<tr><td>Acquisitions</td><td>({tagged("10", tag="ex:Acquisitions", attributes="scale=\"3\"")}</td><td>)</td></tr>',
        row("Concept negative, displayed positive", tagged("25", tag="ex:ConceptNegative", attributes='sign="-"')),
        row("Reported zero", tagged("-", tag="ex:Zero", attributes='format="ixt:zerodash"')),
        row("Ambiguous dash", tagged("--", tag="ex:NotZero")),
    ]))
    result = {found.tag: found for found in parse_filing_html(document(body), FILING)}
    assert result["us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"].value == 12_715_000_000
    assert result["us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"].presentation_value == -12_715_000_000
    assert result["ex:Acquisitions"].value == 10_000
    assert result["ex:Acquisitions"].presentation_value == -10_000
    assert result["ex:ConceptNegative"].value == -25
    assert result["ex:ConceptNegative"].presentation_value == 25
    assert result["ex:Zero"].value == 0
    assert "ex:NotZero" not in result


def test_balance_instant_annual_endpoint_only_and_eps_unit():
    body = table("Consolidated Balance Sheets", "".join([
        row("Total assets", tagged("500", context="instant", tag="us-gaap:Assets")),
        row("Quarter-end assets", tagged("490", context="quarterinstant", tag="ex:QuarterAssets")),
        row("Duration balance invalid", tagged("480", tag="ex:DurationAssets")),
    ])) + table("Consolidated Statements of Income", row("Diluted earnings per share", tagged("3.25", tag="us-gaap:EarningsPerShareDiluted", unit="eps")))
    result = parse_filing_html(document(body), FILING)
    assert {found.tag for found in result} == {"us-gaap:Assets", "us-gaap:EarningsPerShareDiluted"}
    assert next(found for found in result if "Earnings" in found.tag).unit == "USD/shares"


def test_comment_markup_and_fragmented_word_headings_within_main_section():
    body = '<p>ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA</p><p><span>INC</span><span>OME STATEMENTS</span></p><!-- generated table -->' + "<table>" + row("Revenue", tagged()) + "</table>"
    assert len(parse_filing_html(document(body), FILING)) == 1


def test_note_section_copied_main_title_and_mda_selected_table_not_extracted():
    selected = table("Selected Consolidated Balance Sheets data", row("Assets", tagged("100", context="instant", tag="us-gaap:Assets")))
    main = table("Consolidated Statements of Income", row("Revenue", tagged("200")))
    notes = '<h2>Notes to Consolidated Financial Statements</h2>' + table("Consolidated Statements of Income", row("Summarized subsidiary revenue", tagged("999", tag="ex:Subsidiary")))
    result = parse_filing_html(document(selected + main + notes), FILING)
    assert len(result) == 1
    assert result[0].value == 200


def test_quarterly_filing_rejected_despite_annual_comparative():
    body = table("Consolidated Statements of Income", row("Revenue", tagged()))
    assert parse_filing_html(document(body), replace(FILING, form="10-Q")) == []


def test_companyfacts_rejects_quarters_dimensions_units_remain_separate():
    annual = {"val": 100, "start": "2023-01-01", "end": "2023-12-31", "form": "10-K", "filed": FILING.filed, "accn": FILING.accession}
    payload = {"cik": "123456", "facts": {"us-gaap": {
        "Revenues": {"label": "Reported revenue", "units": {"USD": [annual, {**annual, "start": "2023-10-01", "val": 30}, {**annual, "form": "10-Q", "val": 101}, {**annual, "val": float("inf")}], "EUR": [{**annual, "val": 91}]}},
        "Assets": {"label": "Assets", "units": {"USD": [{key: value for key, value in annual.items() if key != "start"}, {**annual, "start": None, "end": "2023-09-30", "val": 99}]}},
    }, "ex": {"UnmappedCustom": {"units": {"USD": [annual]}}}}}
    result = parse_company_facts(payload, [FILING])
    assert {(found.tag, found.unit, found.value) for found in result} == {("us-gaap:Revenues", "USD", 100), ("us-gaap:Revenues", "EUR", 91), ("us-gaap:Assets", "USD", 100)}


def test_xbrl_instance_keeps_standard_annuals_only_and_no_external_entity():
    xml = b'''<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2023" xmlns:ex="http://example.test/custom">
    <xbrli:context id="a"><xbrli:period><xbrli:startDate>2023-01-01</xbrli:startDate><xbrli:endDate>2023-12-31</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
    <us-gaap:Revenues contextRef="a" unitRef="usd">2500000</us-gaap:Revenues>
    <ex:CustomMetric contextRef="a" unitRef="usd">1000000</ex:CustomMetric></xbrli:xbrl>'''
    result = parse_xbrl_instance(xml, FILING)
    assert len(result) == 1
    assert result[0].value == 2_500_000
    assert result[0].tag == "us-gaap:Revenues"


def test_untagged_annual_table_scale_eps_section_and_missing_dashes():
    filing = replace(FILING, report_date="2024-12-31", filed="2025-02-15")
    content = b'''<h2>Consolidated Statements of Income</h2><!-- generated markup -->
    <p>Years ended December 31 (in millions, except per share amounts), USD</p>
    <table><tr><td></td><td>2024</td><td>2023</td></tr>
    <tr><td>Revenue</td><td>$ 1,000</td><td>$ 900</td></tr>
    <tr><td>Unreported</td><td>-</td><td>--</td></tr>
    <tr><td>Earnings per share</td><td></td><td></td></tr>
    <tr><td>Basic</td><td>3.25</td><td>3.00</td></tr>
    <tr><td>Diluted</td><td>3.10</td><td>2.90</td></tr>
    <tr><td>Weighted average shares</td><td></td><td></td></tr>
    <tr><td>Basic</td><td>180</td><td>175</td></tr></table>'''
    result = parse_filing_html(content, filing)
    assert len(result) == 6
    by_label = {found.label: found for found in result if found.end == "2024-12-31"}
    assert by_label["Revenue"].value == 1_000_000_000
    assert by_label["Basic"].unit == "USD/shares"
    assert by_label["Basic"].value == 3.25
    assert by_label["Diluted"].value == 3.10
    assert "Unreported" not in by_label


def test_untagged_table_without_explicit_period_dates_is_unsupported():
    content = b'''<h2>Consolidated Statements of Income</h2><p>Annual amounts in millions USD</p>
    <table><tr><td></td><td>2024</td><td>2023</td></tr><tr><td>Revenue</td><td>1,000</td><td>900</td></tr></table>'''
    assert parse_filing_html(content, replace(FILING, report_date="2024-12-31", filed="2025-02-15")) == []


def test_latest_comparative_changes_are_recorded_without_claiming_restatement():
    later = replace(FILING, accession="0000123456-25-000001", filed="2025-02-15", report_date="2024-12-31")
    bundle = assemble_bundle(COMPANY, [FILING, later], [fact(), fact(90, filing=later)], [], [])
    selected = bundle.statements[STATEMENTS[0]][0].values["2023-12-31"]
    assert selected.value == 90
    assert selected.accession == later.accession
    assert "may reflect a restatement or reclassification" in selected.selection_reason
    assert len(bundle.raw_facts) == 2
    assert "2024-12-31" in bundle.periods  # unavailable latest period remains visible


def test_newer_companyfacts_can_supersede_old_native_statement_and_warns():
    later = replace(FILING, accession="0000123456-25-000001", filed="2025-02-15", report_date="2024-12-31")
    bundle = assemble_bundle(COMPANY, [FILING, later], [fact(), fact(90, filing=later, extraction="companyfacts")], [], [])
    assert bundle.statements[STATEMENTS[0]][0].values["2023-12-31"].value == 90
    assert any("fallback" in warning for warning in bundle.warnings)


def test_one_latest_main_presentation_prevents_mixing_old_alternative_tags():
    later = replace(FILING, accession="0000123456-25-000001", filed="2025-02-15", report_date="2024-12-31")
    bundle = assemble_bundle(COMPANY, [FILING, later], [fact(), fact(95, filing=later, tag="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"), fact(95, filing=later, extraction="companyfacts")], [], [])
    assert [row.tag for row in bundle.statements[STATEMENTS[0]]] == ["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"]


def test_ambiguous_same_filing_conflicting_values_and_durations_left_blank():
    ambiguous = [fact(), fact(101), fact(100, start="2023-02-01")]
    bundle = assemble_bundle(COMPANY, [FILING], ambiguous, [], [])
    assert bundle.statements[STATEMENTS[0]] == []
    assert any("Ambiguous" in warning for warning in bundle.warnings)
    assert bundle.periods == ["2023-12-31"]


def test_transition_duration_selected_with_comparison_warning():
    later = replace(FILING, accession="0000123456-24-000002", filed="2024-03-01", form="10-KT")
    bundle = assemble_bundle(COMPANY, [FILING, later], [fact(), fact(80, filing=later, start="2023-03-01")], [], [])
    assert bundle.statements[STATEMENTS[0]][0].values["2023-12-31"].value == 80
    assert any("transition" in warning for warning in bundle.warnings)
    assert any("different annual start dates" in warning for warning in bundle.warnings)


def test_no_fixed_history_cap_and_blank_older_reports():
    ancient = replace(FILING, accession="old", filed="1971-02-15", report_date="1970-12-31")
    oldest = replace(FILING, accession="older", filed="1961-02-15", report_date="1960-12-31")
    bundle = assemble_bundle(COMPANY, [FILING, ancient, oldest], [fact(10, filing=ancient, start="1970-01-01", end="1970-12-31")], [], [])
    assert bundle.periods == ["2023-12-31", "1970-12-31", "1960-12-31"]
    assert bundle.statements[STATEMENTS[0]][0].values["1970-12-31"].value == 10


def test_cash_begin_and_end_keep_instant_dates_and_share_verified_annual_column():
    contexts = '<xbrli:context id="begin"><xbrli:period><xbrli:instant>2022-12-31</xbrli:instant></xbrli:period></xbrli:context>'
    tag = "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
    body = table("Consolidated Statements of Cash Flows", "".join([
        row("Cash from operations", tagged("60", tag="us-gaap:NetCashProvidedByUsedInOperatingActivities")),
        row("Cash, beginning of period", tagged("10", context="begin", tag=tag)),
        row("Cash, end of period", tagged("20", context="instant", tag=tag)),
        row("Cash, beginning of wrong period", tagged("30", context="quarterinstant", tag=tag)),
    ]))
    result = parse_filing_html(document(body, contexts), FILING)
    assert len(result) == 3
    begin = next(found for found in result if found.row_role == "cash_begin")
    end = next(found for found in result if found.row_role == "cash_end")
    assert begin.tag == end.tag == tag
    assert begin.start == end.start == "2023-01-01"
    assert begin.end == end.end == "2023-12-31"
    assert begin.source_instant == "2022-12-31"
    assert end.source_instant == "2023-12-31"
    bundle = assemble_bundle(COMPANY, [FILING], result, [], [])
    assert len(bundle.statements[STATEMENTS[2]]) == 3
    assert {row.values["2023-12-31"].row_role for row in bundle.statements[STATEMENTS[2]]} == {"", "cash_begin", "cash_end"}


def test_cash_instant_not_assigned_to_ambiguous_annual_column():
    contexts = '<xbrli:context id="otherannual"><xbrli:period><xbrli:startDate>2023-02-01</xbrli:startDate><xbrli:endDate>2023-12-31</xbrli:endDate></xbrli:period></xbrli:context>'
    body = table("Consolidated Statements of Cash Flows", "".join([
        row("Cash from operations", tagged("60", tag="us-gaap:NetCashProvidedByUsedInOperatingActivities")),
        row("Other annual cashflow", tagged("15", context="otherannual", tag="ex:OtherCashFlow")),
        row("Cash, end of period", tagged("20", context="instant", tag="us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")),
    ]))
    assert all(not found.row_role for found in parse_filing_html(document(body, contexts), FILING))


def test_future_duration_cannot_map_current_cash_to_a_future_annual_period():
    contexts = '<xbrli:context id="future"><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>'
    body = table("Consolidated Statements of Cash Flows", "".join([
        row("Future projected cashflow", tagged("60", context="future", tag="ex:FutureCashFlow")),
        row("Cash, beginning of period", tagged("20", context="instant", tag="us-gaap:CashAndCashEquivalentsAtCarryingValue")),
    ]))
    assert parse_filing_html(document(body, contexts), FILING) == []


@pytest.mark.parametrize("form", ["20-F", "40-F"])
def test_foreign_untagged_dollar_currency_requires_explicit_us_dollars(form):
    content = '''<h2>Consolidated Statements of Income</h2><p>Years ended December 31, in millions</p>
    <table><tr><td></td><td>2023</td><td>2022</td></tr><tr><td>Revenue</td><td>$ 100</td><td>$ 90</td></tr></table>'''
    filing = replace(FILING, form=form)
    assert parse_filing_html(content.encode(), filing) == []
    assert len(parse_filing_html(content.replace("in millions", "in millions USD").encode(), filing)) == 2
