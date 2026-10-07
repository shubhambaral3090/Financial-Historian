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

from financial_historian.export import build_workbook
from financial_historian.models import STATEMENTS, Company, StatementBundle
from financial_historian.service import FinancialHistorian

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "data" / "settings.json"
APP_VERSION = "0.1.0"


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
    """Merge settings and replace atomically; never overwrite an unreadable file."""
    try:
        f"{name} {email}".encode("latin-1")
    except UnicodeEncodeError:
        raise ValueError("Use a Latin-letter spelling of your name or organization and an ASCII contact email so the SEC contact can be sent in an HTTP header.") from None
    config, problem = read_settings()
    if problem:
        raise ValueError(problem)
    config.update({"contact_name": name, "contact_email": email})
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=SETTINGS.parent, prefix="settings-", suffix=".tmp", delete=False) as handle:
            json.dump(config, handle, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        os.replace(temporary, SETTINGS)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@st.cache_resource
def get_service(user_agent: str) -> FinancialHistorian:
    return FinancialHistorian(user_agent=user_agent, cache_dir=ROOT / "data" / "cache")


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
    for key in ("bundle", "workbook", "workbook_name"):
        st.session_state.pop(key, None)


def value_periods(bundle: StatementBundle) -> list[str]:
    return sorted({period for rows in bundle.statements.values() for row in rows for period in row.values})


def render_bundle(bundle: StatementBundle) -> None:
    periods = sorted(bundle.periods)
    retrieved_periods = value_periods(bundle)
    if not retrieved_periods:
        st.warning("No annual financial values were extracted. This download contains filing links and coverage notes only; it cannot be used as a statement history.")
    columns = st.columns(3)
    columns[0].metric("Periods with values", len(retrieved_periods))
    columns[1].metric("First retrieved value", retrieved_periods[0] if retrieved_periods else "Unavailable")
    columns[2].metric("Latest retrieved value", retrieved_periods[-1] if retrieved_periods else "Unavailable")
    if periods:
        st.caption(f"Workbook period columns span {periods[0]} to {periods[-1]}. Filing years without extracted values remain visible as blank columns.")
    st.download_button(
        "↓  Download Excel workbook",
        data=st.session_state["workbook"],
        file_name=st.session_state["workbook_name"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
        key="download_workbook",
    )
    st.caption("Workbook includes annual statements, figure-level sources, SEC tags, filing coverage, and retrieval notes. Missing values remain blank.")
    if len(bundle.warnings) > 6:
        st.warning(f"{len(bundle.warnings)} coverage and accounting notices. Review these notes and Sources & Coverage before using the workbook.")
        with st.expander("Review coverage and accounting notices"):
            for warning in bundle.warnings:
                st.write(warning)
    else:
        for warning in bundle.warnings:
            st.warning(warning)
    tabs = st.tabs([*STATEMENTS, "Coverage & sources"])
    for index, statement in enumerate(STATEMENTS):
        with tabs[index]:
            rows = bundle.statements.get(statement, [])
            if not rows:
                st.info("No usable annual figures were extracted for this statement. Review coverage and the linked filings.")
                continue
            display = []
            for row in rows:
                item = {"Line item": row.label, "Unit": row.unit}
                for period in reversed(periods):
                    fact = row.values.get(period)
                    item[period] = (fact.presentation_value if fact.presentation_value is not None else fact.value) if fact else None
                display.append(item)
            st.dataframe(display, hide_index=True, use_container_width=True)
            st.caption("Preview shows reported units without scaling, with the printed statement sign when available. Excel's Data Sheet preserves the underlying reported XBRL value and source details.")
    with tabs[-1]:
        st.markdown("**How historical values are chosen**")
        st.write("For each comparable period, tag, and unit, the app favors the latest eligible annual filing in its retrieved data. A later comparative figure may incorporate a restatement; its presence alone does not prove a restatement. Review filing notes before making analyst adjustments.")
        st.markdown("**Available filing coverage**")
        if bundle.coverage:
            st.dataframe(
                [{"Period end": entry.report_date, "Filed": entry.filed, "Status": entry.status, "Detail": entry.detail, "Filing": entry.source_url} for entry in bundle.coverage],
                column_config={"Filing": st.column_config.LinkColumn("Filing", display_text="Open SEC filing")},
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No filing coverage records were returned. Source details are included for the figures that were retrieved.")
        st.caption("Coverage describes retrieval results, not a guarantee that every historical filing or every original line item has been captured.")


st.set_page_config(page_title="Financial Historian", page_icon="↗", layout="wide", initial_sidebar_state="expanded")
st.markdown(
    """<style>
    .stApp { background: #090d13; color: #e7edf5; }
    .stApp, button, input, textarea, [data-testid="stMetricValue"], h1, h2, h3 {
      font-family: Consolas, 'Cascadia Code', 'SFMono-Regular', monospace !important;
    }
    .block-container { max-width: 1300px; padding-top: 2.25rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] { background: #101720; border-right: 1px solid #253243; }
    [data-testid="stMetric"] { background: #111923; border: 1px solid #263446; border-radius: 8px; padding: 16px; }
    [data-testid="stMetricLabel"] { color: #96a7bd; }
    [data-testid="stMetricValue"] { font-size: 1.55rem; }
    .eyebrow { color: #52d6ba; font-size: .8rem; letter-spacing: .16em; margin-bottom: .6rem; }
    .hero { font-size: clamp(2rem, 5vw, 3rem); font-weight: 600; line-height: 1.15; margin-bottom: .9rem; }
    .intro { color: #aab8c9; line-height: 1.7; max-width: 850px; font-size: .97rem; }
    .selection { background: #111c25; border-left: 3px solid #52d6ba; padding: 18px; border-radius: 4px; margin: 12px 0; }
    .selection-name { font-size: 1.1rem; color: #e7edf5; }
    .selection-meta { color: #92a8be; margin-top: 6px; font-size: .85rem; }
    .footer-note { color: #7f91a8; font-size: .75rem; line-height: 1.7; padding-top: 1rem; }
    </style>""",
    unsafe_allow_html=True,
)

config, settings_problem = read_settings()
environment_contact = os.environ.get("SEC_USER_AGENT", "").strip()
saved_name = str(config.get("contact_name", "")).strip()
saved_email = str(config.get("contact_email", "")).strip()
saved_contact = f"{saved_name} {saved_email}" if saved_name and saved_email else ""
st.session_state["user_agent"] = environment_contact or saved_contact
user_agent = st.session_state["user_agent"]

with st.sidebar:
    st.markdown("### FINANCIAL\n### HISTORIAN")
    st.caption("ANNUAL FINANCIAL RECORDS")
    st.divider()
    st.markdown("**SEC access**")
    if environment_contact:
        st.success("Contact configured by SEC_USER_AGENT.")
    else:
        with st.expander("Contact details" if user_agent else "Set up SEC access", expanded=not bool(user_agent)):
            st.write("The SEC asks automated tools to identify a real name and contact email. No API key or paid account is needed.")
            with st.form("contact_form"):
                name = st.text_input("Your name or organization", value=saved_name, max_chars=120)
                email = st.text_input("Contact email", value=saved_email, max_chars=200)
                contact_submitted = st.form_submit_button("Save contact", use_container_width=True)
            st.caption("Stored only in data/settings.json on this computer and sent to the SEC with requests. Excluded from diagnostic downloads.")
            if contact_submitted:
                if not name.strip() or "\n" in name or "\r" in name:
                    st.error("Enter your name or organization on one line.")
                elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
                    st.error("Enter a valid contact email.")
                elif len(f"{name.strip()} {email.strip()}") > 250:
                    st.error("Keep your name and email to 250 characters combined so the SEC contact fits its request header.")
                else:
                    try:
                        save_contact(name.strip(), email.strip())
                        record("contact_saved")
                        st.rerun()
                    except (OSError, ValueError) as error:
                        st.error(sanitize(error))
        if user_agent:
            st.caption("✓ Contact saved locally")
    if settings_problem:
        st.warning(settings_problem)
    st.divider()
    st.markdown("**Retrieval policy**")
    st.caption("All available annual history\n\nLatest eligible filed values\n\nReported units · source links\n\nNo forecasts or valuation")
    with st.expander("Diagnostics & local files"):
        st.write("SEC responses are cached in data/cache. Operational logs are saved in logs. Downloads below contain this session's sanitized events.")
        st.download_button(
            "Download diagnostic log",
            data="\n".join([f"Financial Historian {APP_VERSION}", f"Python {platform.python_version()} / {platform.system()}", "SEC contact identity omitted.", *st.session_state.get("diagnostics", [])]) + "\n",
            file_name="financial_historian_diagnostics.txt",
            mime="text/plain",
            use_container_width=True,
        )
    st.caption(f"Local edition · v{APP_VERSION}")

st.markdown('<div class="eyebrow">PUBLIC FILINGS / PRIVATE WORKSPACE</div><div class="hero">Financial history, with a paper trail.</div><div class="intro">Find a U.S. public company and export its available annual income statement, balance sheet, and cash flow history to Excel. Every retrieved figure carries its SEC source.</div>', unsafe_allow_html=True)
st.write("")
with st.form("company_search"):
    search_query = st.text_input("Company name, ticker, or CIK", placeholder="e.g. Apple, AAPL, or 320193", max_chars=150)
    submitted = st.form_submit_button("Search companies", type="primary", disabled=not bool(user_agent))

if not user_agent:
    st.info("Start with your SEC contact details in the sidebar, then search for a company.")

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
        st.caption("SELECT A COMPANY")
        for company in results:
            label = f"{company.ticker or 'CIK ' + company.cik}  ·  {company.name}  ·  CIK {company.cik}"
            if st.button(label, key=f"company_{company.cik}_{company.ticker}", use_container_width=True):
                st.session_state["selected_company"] = company
                clear_workbook()
                st.rerun()

selected: Company | None = st.session_state.get("selected_company")
if selected:
    st.markdown(f'<div class="selection"><div class="selection-name">{html.escape(selected.name)}</div><div class="selection-meta">{html.escape(selected.ticker or "No current ticker")} · CIK {html.escape(selected.cik)} · ALL AVAILABLE ANNUAL HISTORY</div></div>', unsafe_allow_html=True)
    st.caption("No year limit is applied. Structured SEC data is strongest from the XBRL era, generally around 2009 onward. Older filings are inspected where supported; unavailable years and unsupported formats are identified in coverage.")
    if "bundle" not in st.session_state:
        if st.button("Prepare Excel download", type="primary", use_container_width=True, disabled=not bool(user_agent)):
            try:
                with st.status("Retrieving annual financial history…", expanded=True) as status:
                    def show_progress(message: str) -> None:
                        st.write(sanitize(message))
                        record("retrieval_progress", message)

                    bundle = get_service(user_agent).generate(selected, progress=show_progress)
                    workbook = build_workbook(bundle)
                    st.session_state["bundle"] = bundle
                    st.session_state["workbook"] = workbook
                    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", selected.ticker or selected.name).strip("_.") or selected.cik
                    st.session_state["workbook_name"] = f"{safe_name}_Financial_History.xlsx"
                    status.update(label="Workbook ready" if value_periods(bundle) else "Coverage report ready · no financial values", state="complete", expanded=False)
                    record("workbook_ready", f"cik={selected.cik} periods={len(bundle.periods)} bytes={len(workbook)}")
            except Exception as error:
                record("generation_failed", f"{type(error).__name__}: {error}")
                st.error(explain_error(error))
    if "bundle" in st.session_state:
        render_bundle(st.session_state["bundle"])
        if st.button("Refresh this company", help="Reload filing indexes and structured facts. Previously filed documents can be reused from the local cache."):
            clear_workbook()
            st.rerun()
elif "results" not in st.session_state:
    st.markdown("#### Your workflow")
    st.write("1. Search and select a company.\n2. Prepare its available annual history.\n3. Download a sourced workbook and review any coverage gaps.")

st.markdown('<div class="footer-note">PUBLIC SEC DATA · VERIFY COVERAGE BEFORE MODELING<br>Original reported line items are preserved where extractable. Banking, insurance, foreign issuers, and older filings can use different taxonomies or formats.</div>', unsafe_allow_html=True)
