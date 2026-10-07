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
    assert any("contact details" in entry.value for entry in app.info)


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
    assert [entry.value for entry in app.metric] == ["1", "2024-12-31", "2024-12-31"]
    assert len(app.get("download_button")) == 2
    assert app.dataframe
    assert app.dataframe[0].value["2024-12-31"].iloc[0] == -1_200_000


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


def test_save_contact_preserves_existing_configuration(ui_file):
    path = ui_file.parent / "data" / "settings.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"existing_option": "preserve"}), encoding="utf-8")
    app = AppTest.from_file(str(ui_file)).run()
    input_field(app, "Your name or organization").input("Offline Fixture")
    input_field(app, "Contact email").input("offline@example.invalid")
    button(app, "Save contact").click().run()
    assert not app.exception
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["existing_option"] == "preserve"
    assert saved["contact_email"] == "offline@example.invalid"
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


def test_unreadable_settings_are_never_overwritten(ui_file):
    path = ui_file.parent / "data" / "settings.json"
    path.parent.mkdir()
    path.write_text("broken-settings", encoding="utf-8")
    app = AppTest.from_file(str(ui_file)).run()
    input_field(app, "Your name or organization").input("Offline Fixture")
    input_field(app, "Contact email").input("offline@example.invalid")
    button(app, "Save contact").click().run()
    assert not app.exception
    assert path.read_text(encoding="utf-8") == "broken-settings"
    assert app.error


def test_overlong_combined_contact_is_rejected_before_save(ui_file):
    app = AppTest.from_file(str(ui_file)).run()
    input_field(app, "Your name or organization").input("x" * 120)
    input_field(app, "Contact email").input("y" * 120 + "@example.invalid")
    button(app, "Save contact").click().run()
    assert not app.exception
    assert any("250 characters" in entry.value for entry in app.error)
    assert not (ui_file.parent / "data" / "settings.json").exists()


def test_header_incompatible_name_is_rejected_before_save(ui_file):
    app = AppTest.from_file(str(ui_file)).run()
    input_field(app, "Your name or organization").input("東京")
    input_field(app, "Contact email").input("offline@example.invalid")
    button(app, "Save contact").click().run()
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
    assert len(app.get("download_button")) == 1
