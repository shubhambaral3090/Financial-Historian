"""Offline UI workflow tests; fixture identities are never sent to the SEC."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from financial_historian.models import Company, CoverageRecord, Fact, StatementBundle, StatementRow
import financial_historian.service


CONTACT = "Offline Fixture offline@example.invalid"


class FixtureHistorian:
    """All calls are in-memory; no requests or fabricated live data."""
    fail = False
    empty = False

    def __init__(self, user_agent: str, cache_dir: Path):
        self.user_agent = user_agent

    def search_companies(self, query: str) -> list[Company]:
        if self.fail:
            raise ValueError(f"Fixture failure for {self.user_agent}")
        return [Company("0000000001", "Fictional UI Fixture", "FIX")]

    def generate(self, company: Company, progress=None) -> StatementBundle:
        if progress:
            progress("Finding annual filings")
            progress("Reading offline fixture")
        source = "https://www.sec.gov/Archives/edgar/data/1/000000000125000001/fixture.htm"
        coverage = CoverageRecord("0000000001-25-000001", "2024-12-31", "2025-02-01", source, "fixture", "Offline test only")
        bundle = StatementBundle(company, periods=[coverage.report_date], coverage=[coverage])
        if self.empty:
            return bundle
        fact = Fact("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "Capital expenditures", "USD", 1_200_000, "2024-01-01", "2024-12-31", coverage.accession, coverage.filed, "10-K", source, "Cash Flow", presentation_value=-1_200_000)
        bundle.periods = [fact.end]
        bundle.statements["Cash Flow"] = [StatementRow(fact.tag, fact.label, fact.unit, {fact.end: fact})]
        bundle.raw_facts = [fact]
        return bundle


@pytest.fixture
def ui_file(tmp_path, monkeypatch):
    """Copy the entry point so settings/logs stay inside an isolated temp folder."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.setattr(financial_historian.service, "FinancialHistorian", FixtureHistorian)
    monkeypatch.setattr(FixtureHistorian, "fail", False)
    monkeypatch.setattr(FixtureHistorian, "empty", False)
    st.cache_resource.clear()
    file = tmp_path / "app.py"
    file.write_text((Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8"), encoding="utf-8")
    yield file
    st.cache_resource.clear()


def button(app: AppTest, label: str):
    return next(element for element in app.button if element.label == label)


def input_field(app: AppTest, label: str):
    return next(element for element in app.text_input if element.label == label)


def choose_fixture(app: AppTest) -> AppTest:
    input_field(app, "Company name, ticker, or CIK").input("FIX")
    button(app, "Search companies").click().run()
    next(element for element in app.button if "Fictional UI Fixture" in element.label).click().run()
    return app


def test_first_run_requires_contact_without_network(ui_file):
    app = AppTest.from_file(str(ui_file)).run()
    assert not app.exception
    assert button(app, "Search companies").disabled
    assert any("SEC contact" in entry.value for entry in app.info)


def test_search_selection_generates_real_workbook_from_offline_fixture(ui_file, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", CONTACT)
    app = choose_fixture(AppTest.from_file(str(ui_file)).run())
    button(app, "Prepare Excel download").click().run()
    assert not app.exception
    workbook = app.session_state["workbook"]
    assert workbook.startswith(b"PK")
    with ZipFile(BytesIO(workbook)) as archive:
        assert "xl/workbook.xml" in archive.namelist()
    assert app.session_state["workbook_name"] == "FIX_Financial_History.xlsx"
    assert [entry.value for entry in app.metric] == ["1", "2024", "2024"]
    assert [entry.label for entry in app.metric] == ["Periods with figures", "Earliest figures", "Latest figures"]
    assert len(app.get("download_button")) == 2
    assert app.dataframe
    preview = " ".join(element.proto.body for element in app.get("html"))
    assert "<td>(1.2)</td>" in preview
    assert "USD million" in preview
    assert "2024-12-31" in preview
    assert any(entry.value == "Your workbook is ready" for entry in app.subheader)
    assert any(entry.label == "Retrieval details" and not entry.proto.expanded for entry in app.expander)
    assert any("Building the Excel workbook" in line for line in app.session_state["retrieval_messages"])


def test_failed_search_has_sanitized_error_and_diagnostics(ui_file, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", CONTACT)
    monkeypatch.setattr(FixtureHistorian, "fail", True)
    app = AppTest.from_file(str(ui_file)).run()
    input_field(app, "Company name, ticker, or CIK").input("FIX")
    button(app, "Search companies").click().run()
    assert not app.exception
    assert app.error
    error = " ".join(entry.value for entry in app.error)
    diagnostics = "\n".join(app.session_state["diagnostics"])
    assert "Fixture failure" in error
    assert CONTACT not in error + diagnostics
    assert "offline@example.invalid" not in error + diagnostics


def test_contact_is_session_only_and_does_not_write_settings(ui_file):
    path = ui_file.parent / "data" / "settings.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"existing_option": "preserve"}), encoding="utf-8")
    app = AppTest.from_file(str(ui_file)).run()
    input_field(app, "Your name or organization").input("Offline Fixture")
    input_field(app, "Contact email").input("offline@example.invalid")
    button(app, "Continue to Financial Historian").click().run()
    assert not app.exception
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["existing_option"] == "preserve"
    assert "contact_email" not in saved
    assert app.session_state["contact_email"] == "offline@example.invalid"
    assert not button(app, "Search companies").disabled
    assert "offline@example.invalid" not in "\n".join(app.session_state["diagnostics"])


def test_coverage_only_report_is_downloadable_and_explicit(ui_file, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", CONTACT)
    monkeypatch.setattr(FixtureHistorian, "empty", True)
    app = choose_fixture(AppTest.from_file(str(ui_file)).run())
    button(app, "Prepare Excel download").click().run()
    assert not app.exception
    assert app.session_state["workbook"].startswith(b"PK")
    assert any("No annual financial values" in entry.value for entry in app.warning)
    assert app.metric[0].value == "0"


def test_unreadable_settings_do_not_block_session_contact(ui_file):
    path = ui_file.parent / "data" / "settings.json"
    path.parent.mkdir()
    path.write_text("broken-settings", encoding="utf-8")
    app = AppTest.from_file(str(ui_file)).run()
    input_field(app, "Your name or organization").input("Offline Fixture")
    input_field(app, "Contact email").input("offline@example.invalid")
    button(app, "Continue to Financial Historian").click().run()
    assert not app.exception
    assert path.read_text(encoding="utf-8") == "broken-settings"
    assert app.session_state["contact_email"] == "offline@example.invalid"


def test_overlong_combined_contact_is_rejected_before_save(ui_file):
    app = AppTest.from_file(str(ui_file)).run()
    input_field(app, "Your name or organization").input("x" * 120)
    input_field(app, "Contact email").input("y" * 120 + "@example.invalid")
    button(app, "Continue to Financial Historian").click().run()
    assert not app.exception
    assert any("250 characters" in entry.value for entry in app.error)
    assert not (ui_file.parent / "data" / "settings.json").exists()


def test_header_incompatible_name_is_rejected_before_save(ui_file):
    app = AppTest.from_file(str(ui_file)).run()
    input_field(app, "Your name or organization").input("東京")
    input_field(app, "Contact email").input("offline@example.invalid")
    button(app, "Continue to Financial Historian").click().run()
    assert not app.exception
    assert any("HTTP header" in entry.value for entry in app.error)
    assert not (ui_file.parent / "data" / "settings.json").exists()


def test_new_search_clears_previously_prepared_company_workbook(ui_file, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", CONTACT)
    app = choose_fixture(AppTest.from_file(str(ui_file)).run())
    button(app, "Prepare Excel download").click().run()
    assert app.session_state["workbook"]
    monkeypatch.setattr(FixtureHistorian, "search_companies", lambda self, query: [])
    input_field(app, "Company name, ticker, or CIK").input("NONE")
    button(app, "Search companies").click().run()
    assert not app.exception
    assert "workbook" not in app.session_state
    assert "bundle" not in app.session_state
    assert "selected_company" not in app.session_state
    assert "retrieval_messages" not in app.session_state
    assert len(app.get("download_button")) == 1


def test_generation_failure_does_not_leave_a_partial_workbook(ui_file, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", CONTACT)
    def fail_after_progress(self, company, progress=None):
        progress("Reading fixture")
        raise ValueError(f"Fixture generation failure for {self.user_agent}")
    monkeypatch.setattr(FixtureHistorian, "generate", fail_after_progress)
    app = choose_fixture(AppTest.from_file(str(ui_file)).run())
    button(app, "Prepare Excel download").click().run()
    assert not app.exception
    assert "workbook" not in app.session_state
    assert "bundle" not in app.session_state
    assert "retrieval_messages" not in app.session_state
    assert any("Fixture generation failure" in entry.value for entry in app.error)
    assert CONTACT not in " ".join(entry.value for entry in app.error)


def test_coverage_exposes_years_without_values_instead_of_counting_them(ui_file, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", CONTACT)
    original_generate = FixtureHistorian.generate
    def generate_with_gap(self, company, progress=None):
        bundle = original_generate(self, company, progress)
        bundle.periods.insert(0, "1994-12-31")
        bundle.warnings = ["An older filing could not be extracted."]
        return bundle
    monkeypatch.setattr(FixtureHistorian, "generate", generate_with_gap)
    app = choose_fixture(AppTest.from_file(str(ui_file)).run())
    button(app, "Prepare Excel download").click().run()
    assert not app.exception
    assert app.metric[0].value == "1"
    assert any("1 discovered annual period has no extracted figures" in entry.value for entry in app.info)
    assert any(entry.label == "Coverage & notes" and not entry.proto.expanded for entry in app.expander)
    assert any("1994-12-31" in entry.value for entry in app.markdown)
    assert "aria-label='Unavailable'>—" in " ".join(element.proto.body for element in app.get("html"))


def test_statement_preview_escapes_reported_labels(ui_file, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", CONTACT)
    original_generate = FixtureHistorian.generate
    def generate_with_special_label(self, company, progress=None):
        bundle = original_generate(self, company, progress)
        row = bundle.statements["Cash Flow"][0]
        row.label = "<script>alert('fixture')</script> & capital expenditures"
        row.section = "Investing <activities>"
        row.is_total = True
        return bundle
    monkeypatch.setattr(FixtureHistorian, "generate", generate_with_special_label)
    app = choose_fixture(AppTest.from_file(str(ui_file)).run())
    button(app, "Prepare Excel download").click().run()
    assert not app.exception
    preview = " ".join(element.proto.body for element in app.get("html"))
    assert "<script>" not in preview
    assert "&lt;script&gt;" in preview
    assert "Investing &lt;activities&gt;" in preview
    assert "statement-total" in preview
