"""Local browser interface for Financial Historian."""
from __future__ import annotations

import html
import json
import logging
import os
import platform
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from financial_historian import __version__
from financial_historian.export import CURRENCIES, build_workbook
from financial_historian.models import STATEMENTS, Company, StatementBundle
from financial_historian.market import YahooFinanceProvider
from financial_historian.service import FinancialHistorian, limit_statement_history
from financial_historian.universe import UniverseProvider

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "data" / "settings.json"
APP_VERSION = __version__


def sanitize(text: object) -> str:
    """Share operational details without exposing the configured SEC identity."""
    value = str(text)
    for identity in (os.environ.get("SEC_USER_AGENT", ""), st.session_state.get("user_agent", "")):
        if identity:
            value = value.replace(identity, "[SEC contact removed]")
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email removed]", value)
    value = re.sub(r"(?i)(authorization|api[_-]?key|token|password)\s*[:=]\s*\S+", r"\1=[removed]", value)
    return value


@st.cache_resource
def get_logger() -> logging.Logger:
    logger = logging.getLogger("financial_historian.ui")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        try:
            from logging.handlers import RotatingFileHandler

            log_dir = ROOT / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(log_dir / "app.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
        except OSError:
            logger.addHandler(logging.NullHandler())
    return logger


def record(event: str, detail: object = "") -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {event} {sanitize(detail)}".rstrip()
    events = st.session_state.setdefault("diagnostics", [])
    events.append(line)
    del events[:-150]
    get_logger().info("%s %s", event, sanitize(detail))


def read_settings() -> tuple[dict, str]:
    try:
        if SETTINGS.exists():
            config = json.loads(SETTINGS.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("Settings must be a JSON object.")
            return config, ""
    except (OSError, ValueError):
        return {}, "Your local settings file could not be read. It has been preserved. Use SEC_USER_AGENT or repair data/settings.json before saving a contact."
    return {}, ""


def save_contact(name: str, email: str) -> None:
    """Keep the SEC contact in this session; it is not persisted by default."""
    try:
        f"{name} {email}".encode("latin-1")
    except UnicodeEncodeError:
        raise ValueError("Use a Latin-letter spelling of your name or organization and an ASCII contact email so the SEC contact can be sent in an HTTP header.") from None
    st.session_state["user_agent"] = f"{name.strip()} {email.strip()}"
    st.session_state["contact_name"] = name.strip()
    st.session_state["contact_email"] = email.strip()


@st.cache_resource
def get_service(user_agent: str) -> FinancialHistorian:
    return FinancialHistorian(user_agent=user_agent, cache_dir=ROOT / "data" / "cache")


@st.cache_resource
def get_universe() -> UniverseProvider:
    return UniverseProvider()


@st.cache_resource
def get_market_provider() -> YahooFinanceProvider:
    return YahooFinanceProvider()


def explain_error(error: Exception) -> str:
    detail = sanitize(error)
    lowered = detail.lower()
    if "403" in lowered or "forbidden" in lowered or "blocked" in lowered:
        return "The SEC refused this request. Check your contact details and internet connection. If your network blocks SEC access, try again from your Windows PC. " + detail
    if "429" in lowered or "rate" in lowered and "limit" in lowered:
        return "The SEC is limiting requests. Wait briefly, then try again. Cached data will be reused where possible. " + detail
    if "timeout" in lowered or "timed out" in lowered or "connection" in lowered:
        return "The SEC could not be reached. Check your internet connection, then try again. " + detail
    if "certificate" in lowered or "ssl" in lowered:
        return "The secure connection to the SEC could not be verified. Check your system clock and trusted certificates. " + detail
    return "The workbook could not be prepared. " + detail


def clear_workbook() -> None:
    for key in ("bundle", "workbook", "workbook_name", "retrieval_messages"):
        st.session_state.pop(key, None)


def value_periods(bundle: StatementBundle) -> list[str]:
    return sorted({period for rows in bundle.statements.values() for row in rows for period in row.values})


def render_bundle(bundle: StatementBundle) -> None:
    periods = sorted(bundle.periods)
    retrieved_periods = value_periods(bundle)
    with st.container(border=True):
        st.subheader("Your workbook is ready" if retrieved_periods else "Your coverage report is ready")
        st.caption(st.session_state["workbook_name"])
        st.download_button(
            "Download Excel workbook",
            data=st.session_state["workbook"],
            file_name=st.session_state["workbook_name"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
            key="download_workbook",
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

    st.subheader("Statement preview")
    st.caption("Currency amounts in millions; per-share figures and share counts retain their reported units. Scroll across for older years. A dash means unavailable.")
    tabs = st.tabs(["Income statement", "Balance sheet", "Cash flow"])
    for index, statement in enumerate(STATEMENTS):
        with tabs[index]:
            rows = bundle.statements.get(statement, [])
            if not rows:
                st.info("No usable annual figures were extracted for this statement. Review coverage and the linked filings.")
                continue
            columns = "".join(f"<th scope='col'>{html.escape(period)}</th>" for period in reversed(periods))
            body = []
            previous_section = ""
            for row in rows:
                if row.section and row.section != previous_section:
                    body.append(f"<tr class='statement-section'><th scope='row'>{html.escape(row.section)}</th><td colspan='{len(periods) + 1}'></td></tr>")
                    previous_section = row.section
                is_currency = row.unit in CURRENCIES
                unit = f"{row.unit} million" if is_currency else row.unit
                cells = []
                for period in reversed(periods):
                    fact = row.values.get(period)
                    if fact is None:
                        cells.append("<td class='missing' aria-label='Unavailable'>—</td>")
                        continue
                    value = fact.presentation_value if fact.presentation_value is not None else fact.value
                    value = value / 1_000_000 if is_currency else value
                    number = f"{abs(value):,.6f}".rstrip("0").rstrip(".")
                    text = f"({number})" if value < 0 else number
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


config, settings_problem = read_settings()
environment_contact = os.environ.get("SEC_USER_AGENT", "").strip()
saved_name = str(st.session_state.get("contact_name", "")).strip()
saved_email = str(st.session_state.get("contact_email", "")).strip()
user_agent = environment_contact or str(st.session_state.get("user_agent", "")).strip()

st.set_page_config(page_title="Financial Historian", page_icon="📄", layout="wide", initial_sidebar_state="collapsed" if user_agent else "expanded")
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
    [data-testid="stForm"] { border: none; padding: 0; }
    [data-testid="stVerticalBlockBorderWrapper"] > div { border-radius: 14px; }
    .brand { color: #35373b; font-size: 1rem; font-weight: 600; letter-spacing: -.02rem; }
    .welcome { max-width: 780px; margin: 3rem auto 1.6rem; text-align: center; }
    .welcome p { color: #686b70; line-height: 1.65; font-size: 1rem; max-width: 620px; margin: 0 auto; }
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

with st.sidebar:
    st.markdown("### Financial Historian")
    st.caption("Your local financial research workspace")
    st.divider()
    st.markdown("**SEC connection**")
    st.caption("✓ Contact active for this session" if user_agent else "Contact is requested once per browser session")
    with st.expander("Market suggestions"):
        st.caption("Load the supported S&P 500 and Nasdaq-100 directory when you want suggestions.")
        if st.button("Refresh company universe", width="stretch"):
            try:
                st.session_state["universe"] = get_universe().load()
                record("universe_loaded", f"members={len(st.session_state['universe'])}")
            except Exception as error:
                st.error("The company universe could not be refreshed. " + sanitize(error))
        for member in st.session_state.get("universe", [])[:8]:
            if st.button(f"{member.company.ticker} · {member.company.name}", key=f"suggest_{member.company.cik}_{member.company.ticker}", width="stretch"):
                st.session_state["selected_company"] = member.company
                clear_workbook()
                st.rerun()
    if settings_problem:
        st.warning(settings_problem)
    st.divider()
    with st.expander("About the data"):
        st.write("The app presents the latest 20 fiscal periods for supported S&P 500 and Nasdaq-100 companies. Each retrieved figure includes a source filing. Older and unsupported filings can leave gaps, which are recorded in the workbook.")
        st.caption("Latest eligible filed values · Original reported units · No forecasts or valuations")
    with st.expander("Help & diagnostics"):
        st.write("Use Extract All on the downloaded ZIP before opening launch_windows.cmd. Keep this browser tab open while a workbook is being prepared.")
        st.caption("Local files: data/settings.json for contact details, data/cache for SEC responses, and logs for operational events.")
        st.download_button(
            "Download diagnostic log",
            data="\n".join([f"Financial Historian {APP_VERSION}", f"Python {platform.python_version()} / {platform.system()}", "SEC contact identity omitted.", *st.session_state.get("diagnostics", [])]) + "\n",
            file_name="financial_historian_diagnostics.txt",
            mime="text/plain",
            width="stretch",
        )
    st.caption(f"Local edition · v{APP_VERSION}")

st.markdown('<div class="brand">Financial Historian</div>', unsafe_allow_html=True)
if not user_agent:
    st.markdown('<div class="contact-card"><h2>Connect to SEC data</h2><p>The SEC requires an identifying name and email for automated requests. No account or API key is needed. This contact stays active for this browser session and is not written to the project files.</p></div>', unsafe_allow_html=True)
    with st.form("first_launch_contact"):
        name_col, email_col = st.columns(2)
        with name_col:
            name = st.text_input("Your name or organization", max_chars=120)
        with email_col:
            email = st.text_input("Contact email", max_chars=200)
        contact_submitted = st.form_submit_button("Continue to Financial Historian", type="primary", width="stretch")
    if contact_submitted:
        if not name.strip() or "\n" in name or "\r" in name:
            st.error("Enter your name or organization on one line.")
        elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
            st.error("Enter a valid contact email.")
        elif len(f"{name.strip()} {email.strip()}") > 250:
            st.error("Keep your name and email to 250 characters combined.")
        else:
            try:
                save_contact(name, email)
                record("contact_session_started")
                st.rerun()
            except ValueError as error:
                st.error(sanitize(error))
if not st.session_state.get("selected_company"):
    st.markdown('<div class="welcome"><h1>Explore a company’s financial history</h1><p>Income statements, balance sheets, and cash flow — across all available annual filings, ready for Excel.</p></div>', unsafe_allow_html=True)
else:
    st.write("")
with st.form("company_search"):
    search_column, button_column = st.columns([5, 1.3], vertical_alignment="bottom")
    with search_column:
        search_query = st.text_input("Company name, ticker, or CIK", placeholder="Search Apple, AAPL, or 320193", max_chars=150)
    with button_column:
        submitted = st.form_submit_button("Search companies", type="primary", width="stretch", disabled=not bool(user_agent))

if not user_agent:
    st.info("Enter your SEC contact above to begin. The contact is used only for this browser session.")

if submitted:
    if not search_query.strip():
        st.warning("Enter a company name, ticker, or CIK to search.")
    else:
        clear_workbook()
        st.session_state.pop("selected_company", None)
        st.session_state.pop("results", None)
        try:
            with st.spinner("Searching SEC company records…"):
                results = get_service(user_agent).search_companies(search_query.strip())
            st.session_state["results"] = results
            record("search_complete", f"matches={len(results)}")
        except Exception as error:
            record("search_failed", f"{type(error).__name__}: {error}")
            st.error(explain_error(error))

if "results" in st.session_state and not st.session_state.get("selected_company"):
    results = st.session_state["results"]
    if not results:
        st.info("No matching company was found. Try its full legal name, ticker, or SEC CIK. The SEC ticker directory may omit delisted companies.")
    else:
        st.caption("Choose a company")
        for company in results:
            label = f"{company.name}  ·  {company.ticker or 'CIK ' + company.cik}"
            if st.button(label, key=f"company_{company.cik}_{company.ticker}", width="stretch"):
                st.session_state["selected_company"] = company
                clear_workbook()
                st.rerun()

selected: Company | None = st.session_state.get("selected_company")
if selected:
    st.markdown(f'<div class="company-name">{html.escape(selected.name)}</div><div class="company-meta">{html.escape(selected.ticker or "No current ticker")} · CIK {html.escape(selected.cik)}</div>', unsafe_allow_html=True)
    if selected.ticker:
        with st.container(border=True):
            market_col, chart_col = st.columns([1, 2])
            with market_col:
                st.subheader("Market data")
                st.caption("Yahoo Finance · latest available close")
                if st.button("Refresh market data", key="refresh_market", width="stretch"):
                    with st.spinner("Loading market data…"):
                        st.session_state["market_quote"] = get_market_provider().quote(selected.ticker)
                quote = st.session_state.get("market_quote")
                if quote and quote.ticker == selected.ticker:
                    if quote.price is None:
                        st.warning("Market data temporarily unavailable. SEC financial statements remain available.")
                    else:
                        st.metric("Latest close", f"{quote.price:,.2f}", f"{quote.change:+,.2f} ({quote.change_percent:+.2f}%)" if quote.change is not None and quote.change_percent is not None else None)
                        st.caption(f"Retrieved {quote.retrieved_at} · {quote.timezone} · {quote.status}")
                else:
                    st.info("Refresh to load the latest available market data.")
            with chart_col:
                if quote and quote.history:
                    st.line_chart({"Close": {point.timestamp: point.close for point in quote.history}}, height=220)
                else:
                    st.caption("The price chart appears after market data is loaded.")
    if "bundle" not in st.session_state:
        st.write("Prepare all available annual history with source links for each figure.")
        st.caption("Large histories can take several minutes. Older filings may have gaps; the workbook explains what was retrieved.")
        if st.button("Prepare Excel download", type="primary", width="stretch", disabled=not bool(user_agent)):
            st.session_state["retrieval_messages"] = []
            try:
                with st.status("Preparing your financial history…", expanded=True) as status:
                    current_step = st.empty()

                    def show_progress(message: str) -> None:
                        safe_message = sanitize(message)
                        current_step.write(safe_message)
                        messages = st.session_state["retrieval_messages"]
                        messages.append(safe_message)
                        del messages[:-150]
                        record("retrieval_progress", message)

                    bundle = get_service(user_agent).generate(selected, progress=show_progress)
                    bundle = limit_statement_history(bundle, 20)
                    show_progress("Building the Excel workbook…")
                    workbook = build_workbook(bundle, progress=show_progress)
                    st.session_state["bundle"] = bundle
                    st.session_state["workbook"] = workbook
                    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", selected.ticker or selected.name).strip("_.") or selected.cik
                    st.session_state["workbook_name"] = f"{safe_name}_Financial_History.xlsx"
                    current_step.empty()
                    status.update(label="Workbook ready" if value_periods(bundle) else "Coverage report ready · no financial values", state="complete", expanded=False)
                    record("workbook_ready", f"cik={selected.cik} periods={len(bundle.periods)} bytes={len(workbook)}")
                    st.rerun()
            except Exception as error:
                clear_workbook()
                record("generation_failed", f"{type(error).__name__}: {error}")
                st.error(explain_error(error))
    if "bundle" in st.session_state:
        render_bundle(st.session_state["bundle"])
        if st.button("Refresh this company", help="Reload filing indexes and structured facts. Previously filed documents can be reused from the local cache."):
            clear_workbook()
            st.rerun()
elif "results" not in st.session_state:
    st.caption("Latest 20 fiscal periods · Three annual statements · SEC sources included")

st.markdown('<div class="footer-note">Financial Historian runs on your computer. Review coverage and source filings before using figures in a model.</div>', unsafe_allow_html=True)
