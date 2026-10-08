"""Automatic, session-private browser research workspace."""
from __future__ import annotations

import html
import os
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import streamlit as st
import altair as alt

from financial_historian import __version__
from financial_historian.analysis_ui import render_analytics
from financial_historian.branding import ASSETS
from financial_historian.contact import browser_contact, validate_contact
from financial_historian.export import CURRENCIES
from financial_historian.models import STATEMENTS, Company, StatementBundle
from financial_historian.market import YahooFinanceProvider
from financial_historian.research import ResearchController
from financial_historian.service import FinancialHistorian
from financial_historian.universe import UniverseProvider, shuffled_suggestions

ROOT = Path(__file__).resolve().parent
APP_VERSION = __version__


def sanitize(text: object) -> str:
    value = str(text)
    for key in ("user_agent", "contact_name", "contact_email"):
        identity = st.session_state.get(key, "")
        if identity:
            value = value.replace(identity, "[SEC contact removed]")
    identity = os.environ.get("SEC_USER_AGENT", "")
    if identity:
        value = value.replace(identity, "[SEC contact removed]")
    return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email removed]", value)


def record(event: str) -> None:
    # Only caller-owned event names, never exception messages or contact values.
    events = st.session_state.setdefault("diagnostics", [])
    events.append(f"{datetime.now(timezone.utc).isoformat()} {event}")
    del events[:-100]


def save_contact(name: str, email: str) -> None:
    st.session_state["user_agent"] = validate_contact(name, email)
    st.session_state["contact_name"] = name.strip()
    st.session_state["contact_email"] = email.strip()


def get_service(user_agent: str) -> FinancialHistorian:
    # Contact-bearing requests.Session belongs only to this browser session.
    if "_sec_service" not in st.session_state:
        st.session_state["_sec_service"] = FinancialHistorian(
            user_agent=user_agent, cache_dir=ROOT / "data" / "cache",
        )
    return st.session_state["_sec_service"]


@st.cache_resource
def get_universe() -> UniverseProvider:
    return UniverseProvider()


@st.cache_resource
def get_market_provider() -> YahooFinanceProvider:
    return YahooFinanceProvider()


@st.cache_resource
def get_controller() -> ResearchController:
    return ResearchController()


def valid_source(url: str) -> bool:
    try:
        value = urlsplit(url)
        return (value.scheme == "https" and value.hostname in {"www.sec.gov", "data.sec.gov"}
                and not value.username and not value.password and value.port in {None, 443})
    except ValueError:
        return False


def clear_workbook() -> None:
    for key in ("research", "bundle", "workbook", "workbook_name", "retrieval_messages", "market_quote"):
        st.session_state.pop(key, None)


def select_company(company: Company) -> None:
    clear_workbook()
    st.session_state["selected_company"] = company
    st.query_params["cik"] = company.cik
    st.query_params["ticker"] = company.ticker
    st.rerun()


def store_workbook(data: bytes, company: Company) -> None:
    st.session_state["workbook"] = data
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", company.ticker or company.cik).strip("_.") or "Company"
    st.session_state["workbook_name"] = f"{safe_name}_Financial_History.xlsx"


@st.dialog("Connect to SEC data", dismissible=False)
def contact_dialog() -> None:
    st.write("The SEC's automated-access policy requires identifying contact information with requests. "
             "Enter your name and email; no API key, password, subscription or payment is needed.")
    st.caption("Kept in this tab's browser session and server-session memory, not in project files. "
               "Browser session-restore settings may retain tab storage after reopening a browser.")
    with st.form("first_launch_contact"):
        name = st.text_input("Your name or organization", max_chars=120)
        email = st.text_input("Contact email", max_chars=200)
        submitted = st.form_submit_button("Continue to Fishtorian", type="primary", width="stretch")
    if submitted:
        try:
            save_contact(name, email)
        except ValueError as error:
            st.error(str(error))
        else:
            record("contact_session_started")
            st.rerun()


def render_heading(company: Company) -> None:
    st.markdown(f'<div class="company-name">{html.escape(company.name)}</div>'
                f'<div class="company-meta">{html.escape(company.ticker or "No current ticker")} · '
                f'CIK {html.escape(company.cik or "pending SEC validation")}</div>', unsafe_allow_html=True)
    snapshot = st.session_state.get("universe")
    matches = [member for member in snapshot.members
               if member.company.ticker.replace(".", "-") == company.ticker.replace(".", "-")] if snapshot else []
    indexes = sorted({index for member in matches for index in member.indexes})
    if snapshot and snapshot.origin == "manual_ticker_groups":
        st.caption("Configured groups: " + (", ".join(indexes) if indexes else "not in the maintained suggestion list"))
        st.caption(f"List maintained {snapshot.maintained_at} · membership is manually configured, not independently verified")
    else:
        st.caption("Index membership: " + (", ".join(indexes) if indexes else "not verified by the configured Yahoo screens"))


def render_quote(quote, error: str = "") -> None:
    if quote is None:
        if error:
            st.warning(error)
        else:
            st.info("No current ticker is available for Yahoo market data. SEC financial history is independent.")
        return
    with st.container(border=True):
        st.subheader("Market context")
        if quote.price is None:
            st.warning("Yahoo Finance market data is unavailable. SEC financial retrieval continues independently. Refresh the browser tab to check again.")
            return
        delta = (f"{quote.change:+,.2f} ({quote.change_percent:+.2f}%)"
                 if quote.change is not None and quote.change_percent is not None else None)
        columns = st.columns([1, 2])
        with columns[0]:
            st.metric(f"{quote.ticker} · {quote.status}", f"{quote.price:,.2f} {quote.currency}".strip(), delta)
            st.caption(f"Yahoo Finance · price as of {quote.as_of or 'unknown'} · {quote.timezone}")
            st.caption(f"Retrieved {quote.retrieved_at} (UTC)")
            if quote.stale:
                st.warning("Showing the last successful Yahoo response; the latest check failed.")
            elif quote.cached:
                st.caption("Valid cached Yahoo response")
        with columns[1]:
            if len(quote.history) >= 2:
                try:
                    st.line_chart({"Price": {point.timestamp: point.close for point in quote.history}}, height=220)
                except Exception:
                    st.info("The chart could not be displayed. The available price is shown alongside it.")
            else:
                st.caption("Not enough valid price observations to draw a chart.")
        st.caption("Quotes may be delayed. Daily movement compares the last two available daily observations; not a guaranteed real-time feed.")


def render_suggestions() -> None:
    snapshot = st.session_state.get("universe")
    if snapshot is None:
        try:
            snapshot = get_universe().load()
            st.session_state["universe"] = snapshot
            st.session_state["suggestions"] = shuffled_suggestions(snapshot, limit=6)
        except Exception:
            st.warning("Yahoo market suggestions are unavailable. Direct SEC search still works.")
            return
    st.caption(snapshot.source)
    if snapshot.origin == "manual_ticker_groups":
        st.caption(f"List maintained {snapshot.maintained_at} · manually configured groups")
    else:
        st.caption("General market screens · not a verified S&P 500 or Nasdaq-100 constituent list")
    if snapshot.retrieved_at:
        st.caption(f"Universe retrieved {snapshot.retrieved_at} (UTC)" + (" · stale fallback" if snapshot.stale else ""))
    if snapshot.origin == "manual_ticker_groups" and not snapshot.stale and snapshot.members:
        st.caption("Incomplete starter lists · membership not independently verified")
        with st.expander("Suggestion-list coverage"):
            for warning in snapshot.warnings:
                st.write(warning)
    else:
        for warning in snapshot.warnings:
            st.warning(warning)
    for member in st.session_state.get("suggestions", []):
        ticker = member.company.ticker
        with st.container(border=True):
            if st.button(f"{ticker} · {member.company.name}", key=f"suggest_{ticker}", width="stretch"):
                select_company(member.company)
            try:
                quote = get_market_provider().quote(ticker, period="1mo")
            except Exception:
                quote = None
            if quote and quote.price is not None:
                st.caption(f"{quote.price:,.2f} {quote.currency}".strip())
                if quote.change is not None and quote.change_percent is not None:
                    positive, negative = quote.change > 0, quote.change < 0
                    color = "#15803d" if positive else "#b91c1c" if negative else "#6b7280"
                    arrow = "▲" if positive else "▼" if negative else "—"
                    st.markdown(f'<span style="color:{color}">{arrow} {quote.change:+,.2f} ({quote.change_percent:+.2f}%)</span>', unsafe_allow_html=True)
                if len(quote.history) >= 2:
                    try:
                        sparkline = alt.Chart(alt.Data(values=[
                            {"date": point.timestamp, "price": point.close} for point in quote.history
                        ])).mark_line(color="#15803d" if (quote.change or 0) >= 0 else "#b91c1c").encode(
                            x=alt.X("date:T", axis=None),
                            y=alt.Y("price:Q", axis=None, scale=alt.Scale(zero=False)),
                        ).properties(height=45)
                        st.altair_chart(sparkline, width="stretch")
                    except Exception:
                        st.caption("Chart unavailable")
                st.caption(f"{quote.status} · {quote.as_of} · {quote.timezone}")
                st.caption(f"Retrieved {quote.retrieved_at} (UTC)" + (" · stale" if quote.stale else ""))
            else:
                st.caption("Price unavailable · select for SEC history")

def value_periods(bundle: StatementBundle) -> list[str]:
    return sorted({period for rows in bundle.statements.values() for row in rows for period in row.values})


def render_bundle(bundle: StatementBundle) -> None:
    periods = sorted(bundle.periods)
    retrieved_periods = value_periods(bundle)
    with st.container(border=True):
        st.subheader(("Your workbook is ready" if retrieved_periods else "Your coverage report is ready") if st.session_state.get("workbook") else "Financial statements")
        if st.session_state.get("workbook"):
            st.download_button(
                "Download Excel workbook", data=st.session_state["workbook"],
                file_name=st.session_state["workbook_name"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", width="stretch", key="download_workbook",
                on_click="ignore",
            )
        if not retrieved_periods:
            st.warning("No annual financial values were extracted. This download contains filing links and coverage notes only; it cannot be used as a statement history.")
        columns = st.columns(3)
        columns[0].metric("Periods with figures", len(retrieved_periods))
        columns[1].metric("Earliest figures", retrieved_periods[0][:4] if retrieved_periods else "Unavailable")
        columns[2].metric("Latest figures", retrieved_periods[-1][:4] if retrieved_periods else "Unavailable")
        st.caption("Annual statements, original reported data, and SEC source links in one file. A period with figures can still have missing line items.")

    empty_periods = sorted(set(periods) - set(retrieved_periods))
    if empty_periods:
        count = len(empty_periods)
        st.info(f"{count} discovered annual {'period has' if count == 1 else 'periods have'} no extracted figures. Review the coverage details below for the missing years and their filings.")
    if bundle.warnings:
        count = len(bundle.warnings)
        st.caption(f"{count} retrieval and accounting {'note is' if count == 1 else 'notes are'} available in Coverage & notes below and in the workbook.")

    render_analytics(bundle, render_statements)


def render_statements(bundle: StatementBundle) -> None:
    periods = sorted(bundle.periods)
    empty_periods = sorted(set(periods) - set(value_periods(bundle)))
    st.subheader("Statement preview")
    st.caption("Currency amounts in millions; per-share figures and share counts retain their reported units. Periods run oldest to newest, matching Excel. Scroll across for later years. A dash means unavailable.")
    tabs = st.tabs(["Income statement", "Balance sheet", "Cash flow"],
                   key="statement_tabs", on_change="rerun")
    for index, statement in enumerate(STATEMENTS):
        with tabs[index]:
            rows = bundle.statements.get(statement, [])
            if not rows:
                st.info("No usable annual figures were extracted for this statement. Review coverage and the linked filings.")
                continue
            columns = "".join(f"<th scope='col'>{html.escape(period)}</th>" for period in periods)
            body = []
            previous_section = ""
            for row in rows:
                if row.section and row.section != previous_section:
                    body.append(f"<tr class='statement-section'><th scope='row'>{html.escape(row.section)}</th><td colspan='{len(periods) + 1}'></td></tr>")
                    previous_section = row.section
                is_currency = row.unit in CURRENCIES
                unit = f"{row.unit} million" if is_currency else row.unit
                cells = []
                for period in periods:
                    fact = row.values.get(period)
                    if fact is None:
                        cells.append("<td class='missing' aria-label='Unavailable'>—</td>")
                        continue
                    value = fact.presentation_value if fact.presentation_value is not None else fact.value
                    value = value / 1_000_000 if is_currency else value
                    number = f"{abs(value):,.6f}".rstrip("0").rstrip(".")
                    text = f"({number})" if value < 0 else number
                    source = html.escape(fact.source_url, quote=True)
                    if valid_source(fact.source_url):
                        cells.append(f"<td><a href='{source}' target='_blank' rel='noopener noreferrer' title='Open SEC source'>{text}</a></td>")
                    else:
                        cells.append(f"<td>{text}</td>")
                emphasis = " class='statement-total'" if row.is_total else ""
                body.append(f"<tr{emphasis}><th scope='row'>{html.escape(row.label)}</th><td class='unit'>{html.escape(unit)}</td>{''.join(cells)}</tr>")
            st.html(
                f"<div class='statement-preview' tabindex='0' role='region' aria-label='{html.escape(statement)} annual history'>"
                f"<table><thead><tr><th scope='col'>Line item</th><th scope='col'>Unit</th>{columns}</tr></thead>"
                f"<tbody>{''.join(body)}</tbody></table></div>"
            )

    with st.expander("Coverage & notes"):
        st.write("The search discovers available annual filings, while statement tabs present the latest 20 fiscal periods. SEC electronic filings and supported formats may cover only part of a company's life.")
        if empty_periods:
            st.write("**No extracted figures:** " + ", ".join(empty_periods))
        if bundle.coverage:
            st.dataframe(
                [{"Period end": entry.report_date, "Filed": entry.filed, "Status": entry.status, "Detail": entry.detail, "Filing": entry.source_url} for entry in bundle.coverage],
                column_config={"Filing": st.column_config.LinkColumn("Filing", display_text="Open SEC filing")},
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No filing coverage records were returned. Source details are included for the figures that were retrieved.")
        if bundle.warnings:
            st.markdown("**Retrieval and accounting notes**")
            for warning in bundle.warnings:
                st.write(sanitize(warning))
        st.markdown("**How values are chosen**")
        st.write("For each comparable historical period, the app favors the latest eligible annual filed values. Later comparatives may reflect restatements, but a later filing alone does not prove one. The workbook preserves original source values and records where each selected figure came from.")
        st.caption("Figures are reported history. No forecasts, valuations, or analyst adjustments are added.")
    messages = st.session_state.get("retrieval_messages", [])
    if messages:
        with st.expander("Retrieval details"):
            st.code("\n".join(messages), language=None)



st.set_page_config(page_title="Fishtorian", page_icon=str(ASSETS / "fishtorian-mark.svg"), layout="wide", initial_sidebar_state="auto")
st.markdown(
    """<style>
    .stApp { background: #ffffff; color: #202123; }
    .stApp, button, input, textarea, h1, h2, h3 {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }
    .block-container { max-width: 1100px; padding-top: 2.8rem; padding-bottom: 2rem; }
    [data-testid="stAppDeployButton"] { display: none; }
    [data-testid="stSidebar"] { background: #f7f7f8; border-right: 1px solid #ececee; }
    [data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }
    h1 { font-size: clamp(1.8rem, 4vw, 2.5rem) !important; font-weight: 600 !important; letter-spacing: -.055rem; }
    h2, h3 { letter-spacing: -.02rem; }
    [data-testid="stMetricValue"] { font-size: 1.65rem; font-weight: 600; }
    [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"] { color: #686b70; }
    [data-testid="stCaptionContainer"] p { color: #62666b; }
    [data-testid="stForm"] { border: none; padding: 0; }
    [data-testid="stVerticalBlockBorderWrapper"] > div { border-radius: 14px; }
    .brand { color: #35373b; font-size: 1rem; font-weight: 600; letter-spacing: -.02rem; }
    .welcome { max-width: 780px; margin: 3rem auto 1.6rem; text-align: center; }
    .welcome p { color: #686b70; line-height: 1.65; font-size: 1rem; max-width: 620px; margin: 0 auto; }
.statement-preview a { color: inherit; text-decoration: none; border-bottom: 1px dotted #9ca3af; }
    .contact-card { max-width: 760px; margin: 2rem auto 1rem; padding: 1.5rem 1.7rem; border: 1px solid #e5e7eb; border-radius: 14px; background: #f7f7f8; }
    .contact-card p { color: #686b70; line-height: 1.55; margin-bottom: 0; }
    .company-name { color: #202123; font-size: 1.65rem; font-weight: 600; line-height: 1.3; margin: 1.8rem 0 .35rem; }
    .company-meta { color: #686b70; font-size: .9rem; margin-bottom: 1rem; }
    .statement-preview { overflow: auto; max-height: 520px; border: 1px solid #e5e7eb; border-radius: 10px; }
    .statement-preview table { border-collapse: separate; border-spacing: 0; min-width: 100%; font-size: .85rem; font-variant-numeric: tabular-nums; }
    .statement-preview th, .statement-preview td { padding: 10px 14px; border-bottom: 1px solid #eceef0; white-space: nowrap; text-align: right; }
    .statement-preview thead th { position: sticky; top: 0; background: #f7f7f8; z-index: 2; font-weight: 500; color: #686b70; }
    .statement-preview th:first-child { position: sticky; left: 0; min-width: 230px; max-width: 340px; white-space: normal; text-align: left; background: white; z-index: 1; font-weight: 400; border-right: 1px solid #eceef0; }
    .statement-preview thead th:first-child { z-index: 3; background: #f7f7f8; }
    .statement-preview thead th:nth-child(2) { text-align: left; }
    .statement-preview .unit { color: #686b70; font-size: .8rem; text-align: left; }
    .statement-preview .missing { color: #a0a3a8; }
    .statement-preview .statement-total > * { font-weight: 600; border-top: 1px solid #d9dde2; }
    .statement-preview .statement-section > * { background: #f3f4f5; font-weight: 600; color: #555a61; }
    .statement-preview .statement-total th:first-child { font-weight: 600; }
    .statement-preview .statement-section th:first-child { background: #f3f4f5; font-weight: 600; }
    .footer-note { color: #85878c; font-size: .78rem; text-align: center; padding-top: 2.5rem; }
    @media (max-width: 700px) {
      .block-container { padding-top: 3.4rem; }
      .welcome { margin-top: 1.8rem; }
      [data-testid="stHorizontalBlock"] { flex-direction: column; }
      [data-testid="stColumn"] { width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
    }
    </style>""",
    unsafe_allow_html=True,
)

environment_contact = os.environ.get("SEC_USER_AGENT", "").strip()
if not environment_contact:
    session_contact = ({"name": st.session_state["contact_name"], "email": st.session_state["contact_email"]}
                       if st.session_state.get("contact_name") else None)
    bridge = browser_contact(session_contact)
    if not st.session_state.get("user_agent"):
        if bridge is None:
            st.caption("Restoring this tab's private session…")
            st.stop()
        recovered = bridge.get("contact")
        if isinstance(recovered, dict):
            try:
                save_contact(str(recovered.get("name", "")), str(recovered.get("email", "")))
            except ValueError:
                pass
    if bridge and bridge.get("storageAvailable") is False:
        st.info("Browser session storage is disabled. Contact will be requested again after a full tab refresh.")
user_agent = environment_contact or st.session_state.get("user_agent", "")

with st.sidebar:
    st.markdown("### Fishtorian")
    st.caption("Your private financial research workspace")
    st.divider()
    suggestion_area = st.container()
    st.divider()
    with st.expander("About the data"):
        st.write("Latest 20 fiscal periods · SEC source links · Reported units · No forecasts or valuation")
        st.caption("SEC and Yahoo Finance are separate providers. Missing or unsupported data stays explicit.")
    with st.expander("Help & diagnostics"):
        st.write("Select a company and the page loads automatically. Download its workbook when ready. "
                 "Refresh the browser tab for a new data check.")
        st.caption("SEC contact is session-only. The bounded SEC response cache contains public records, not your contact.")
        st.download_button(
            "Download diagnostic log",
            data="\n".join([f"Fishtorian {APP_VERSION}",
                           f"Python {platform.python_version()} / {platform.system()}",
                           "SEC contact identity omitted.", *st.session_state.get("diagnostics", [])]),
            file_name="financial_historian_diagnostics.txt", mime="text/plain", width="stretch",
        )
    st.caption(f"Web edition · v{APP_VERSION}")

st.image(str(ASSETS / "fishtorian.svg"),width=270)
if not user_agent:
    st.markdown('<div class="welcome"><h1>Your financial research workspace</h1>'
                '<p>Sourced annual statements, market context, and a clean Excel workbook.</p></div>',
                unsafe_allow_html=True)
    contact_dialog()
    st.stop()

if "selected_company" not in st.session_state:
    cik, ticker = st.query_params.get("cik", ""), st.query_params.get("ticker", "")
    if cik or ticker:
        st.session_state["selected_company"] = Company(cik, ticker or f"CIK {cik}", ticker)

if not st.session_state.get("selected_company"):
    st.markdown('<div class="welcome"><h1>Explore a company’s financial history</h1>'
                '<p>Market context and up to 20 fiscal periods of sourced statements. '
                'Choose a company. We’ll prepare the workbook.</p></div>', unsafe_allow_html=True)

with st.form("company_search"):
    search_column, button_column = st.columns([5, 1.3], vertical_alignment="bottom")
    with search_column:
        search_query = st.text_input("Company name, ticker, or CIK", placeholder="Search Apple, AAPL, or 320193", max_chars=150)
    with button_column:
        submitted = st.form_submit_button("Search companies", type="primary", width="stretch")

if submitted and search_query.strip():
    clear_workbook()
    st.session_state.pop("selected_company", None)
    st.session_state.pop("results", None)
    for key in ("cik", "ticker"):
        st.query_params.pop(key, None)
    try:
        with st.spinner("Searching SEC company records…"):
            st.session_state["results"] = get_service(user_agent).search_companies(search_query.strip())
        record("search_complete")
    except Exception:
        record("search_failed")
        st.error("SEC company search is unavailable. Check your connection and refresh the browser tab to try again.")
elif submitted:
    st.warning("Enter a company name, ticker, or CIK to search.")

if "results" in st.session_state and not st.session_state.get("selected_company"):
    results = st.session_state["results"]
    if not results:
        st.info("No matching company was found. Try its full legal name, ticker, or SEC CIK.")
    else:
        st.caption("Choose a company")
        for company in results:
            if st.button(f"{company.name} · {company.ticker or 'CIK ' + company.cik}", key=f"company_{company.cik}_{company.ticker}", width="stretch"):
                select_company(company)

selected = st.session_state.get("selected_company")
# Loading this bounded/local snapshot does not request six sidebar price charts.
# Its membership labels must be available before the selected heading renders.
if "universe" not in st.session_state:
    try:
        snapshot = get_universe().load()
        st.session_state["universe"] = snapshot
        st.session_state["suggestions"] = shuffled_suggestions(snapshot, limit=6)
    except Exception:
        pass
if selected:
    rendered = {"workbook": False}
    heading_area = st.empty()
    market_area = st.empty()
    financial_area = st.empty()
    with heading_area.container():
        render_heading(selected)
    if "research" not in st.session_state:
        st.session_state["retrieval_messages"] = []
        with st.status("Loading company profile…", expanded=True) as status:
            step = st.empty()

            def on_event(event):
                if event.kind == "progress":
                    message = sanitize(event.message)
                    step.write(message)
                    st.session_state["retrieval_messages"].append(message)
                    del st.session_state["retrieval_messages"][:-100]
                elif event.kind == "company" and event.company:
                    st.session_state["selected_company"] = event.company
                    st.query_params["cik"] = event.company.cik
                    st.query_params["ticker"] = event.company.ticker
                    with heading_area.container():
                        render_heading(event.company)
                elif event.kind == "market":
                    with market_area.container():
                        render_quote(event.quote, event.message)
                elif event.kind == "financial" and event.bundle:
                    st.session_state["bundle"] = event.bundle
                    with financial_area.container():
                        # Static preview can be replaced in the same Streamlit
                        # run. Interactive controls must only be created once.
                        st.info("Statements retrieved. Building schedules and the Excel workbook…")
                        st.caption(f"{len(event.bundle.periods)} selected annual periods. Source checks and the matching workbook are being prepared automatically.")
                elif event.kind == "workbook" and event.workbook and st.session_state.get("bundle"):
                    store_workbook(event.workbook, st.session_state["selected_company"])
                    financial_area.empty()
                    with financial_area.container():
                        render_bundle(st.session_state["bundle"])
                    rendered["workbook"] = True

            try:
                result = get_controller().load(
                    get_service(user_agent), selected, get_market_provider(),
                    force_refresh=True, on_event=on_event,
                )
            except Exception:
                # Fail closed without reflecting contact-bearing service exceptions.
                record("page_failed")
                st.session_state["research"] = None
                status.update(label="Company data could not be loaded. Refresh the browser tab to try again.", state="error", expanded=False)
            else:
                st.session_state["research"] = result
                st.session_state["selected_company"] = result.company
                st.session_state["market_quote"] = result.quote
                if result.bundle:
                    st.session_state["bundle"] = result.bundle
                if result.workbook:
                    store_workbook(result.workbook, result.company)
                status.update(label="Research page ready" if not (result.sec_error or result.market_error or result.workbook_error)
                              else "Research page loaded with coverage notices", state="complete", expanded=False)
                record("page_loaded")
    result = st.session_state.get("research")
    if result:
        with heading_area.container():
            render_heading(result.company)
        with market_area.container():
            render_quote(result.quote, result.market_error)
        if result.sec_stale:
            st.warning("The SEC refresh failed. Showing the last successful statements and their matching workbook, not newly retrieved data.")
        for error in (result.sec_error, result.workbook_error):
            if error:
                st.warning(sanitize(error))
        if result.bundle:
            st.caption(f"SEC retrieved {result.sec_retrieved_at} (UTC)" + (" · last successful cached result" if result.sec_stale else ""))
            if result.workbook:
                st.caption(f"Workbook generated {result.workbook_generated_at} (UTC)")
            if not rendered["workbook"]:
                financial_area.empty()
                with financial_area.container():
                    render_bundle(result.bundle)
        elif result.sec_error:
            with financial_area.container():
                st.info("Financial statements are unavailable for this check. Market context remains independent.")
    else:
        st.error("This page could not finish loading. Refresh the browser tab to try again.")
else:
    st.caption("Latest 20 fiscal periods · Three annual statements · SEC sources included")

with st.sidebar:
    with suggestion_area:
        st.markdown("**Market suggestions**")
        render_suggestions()
st.markdown('<div class="footer-note">Review coverage and original filings before using figures in a financial model.</div>', unsafe_allow_html=True)
