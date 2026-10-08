# Validation record — v0.4.0

Historical record. Current Fishtorian validation and outstanding acceptance gates
are in [RELEASE_v0.7.md](RELEASE_v0.7.md).

Validated October 7, 2026 (America/Indianapolis). Provider timestamps in the
application are explicitly labeled UTC or their exchange timezone.

## Complete suites

| Runtime (Linux) | Result |
| --- | --- |
| Python 3.12.14 | 375 passed, no skips |
| Python 3.13.5 | 375 passed, no skips |
| Python 3.14.6 | 375 passed, no skips |

Dependency compatibility checks passed in all three environments. Python 3.13
uses an isolated uv-created environment; its dependency check used uv because
that environment does not include pip. The reusable cloud setup script was
executed successfully, including installation, dependency check and full tests.

Coverage includes configurable Yahoo screen parsing, overlapping memberships,
local shuffling, last-good fallback, TTL/cooldown/403/429/timeouts/malformed data,
manual-list metadata, ticker/CIK resolution, provider-independent loading,
browser-refresh rechecks, 20-period selection, empty periods, accounting scopes,
continuity, privacy, provenance, chart fallback, and display/export equality.

Review found and fixed three integrity defects before release: partial network
refreshes displacing better cached snapshots; older concurrent refreshes
overwriting newer results; and inconsistent invalid-cell handling between the
browser and workbook. Dedicated regressions cover each.

## Real browser, mocked providers

Chromium/Playwright passed at desktop 1440 × 1100 and mobile 390 × 844 using
fictional in-memory SEC/Yahoo providers. Tests exercise the actual Streamlit app,
custom contact component, browser sessionStorage and downloaded XLSX bytes:

- Centered first-launch contact dialog, then no contact fields on the main page.
- Search/selection automatically loads quotes, statements and Excel.
- Browser reload retains tab contact and selected CIK, and initiates a new check.
- A separate tab requires its own contact.
- Source-linked, signed values and exactly 20 periods match the downloaded Excel.
- No old manual prepare/refresh buttons, document overflow, JavaScript exceptions,
  unexpected external browser requests, or contact in rendered output/download.
- Actual line-chart rendering and compact sidebar sparklines were inspected.

Reproduce with optional `playwright==1.56.0` and installed Chromium:

```bash
.venv/bin/python tests/browser_smoke.py --chromium /usr/bin/chromium
```

This is fixture-backed browser validation, not a live financial-data test.
Screenshots were taken only after the contact dialog closed; user-uploaded files
and generated workbooks are not committed or included in release source archives.

## Workbook comparison

The supplied Apple output was reconstructed offline and compared with the supplied
Reliance Industries layout. Original uploads were not changed. The result has
the 20 selected periods 2006–2025; the clean Data Sheet contains three annual
financial matrices, not the former 18-column raw-fact dump.

The audit workbook contains 1,341 populated Data Sheet values, each with a source
comment and SEC link. All 2,784 displayed-cell references were checked against
Source Data for matching values and source records. Its 7,145 usable source
records remain available separately. Main statement tabs, Data Sheet and browser
use identical selected periods, including entirely blank periods.

LibreOffice-rendered Data Sheets were inspected side by side. The reference has
10 annual columns; the new workbook uses up to 20 and retains company-specific
reported detail. No projections, reference ratios or invented financial values
were copied. Raw facts, source signs and presentation signs remain separate.

The underlying source data still cannot supply earlier income/cash-flow figures
before 2007 in this Apple reconstruction. Its selected 2007 balance sheet also
has a previously identified 1 million USD disagreement across filing vintages.
These are explicit data/coverage limitations, not solved by formatting.

## Windows and Python compatibility

Launcher regressions pass on all three runtimes. It selects a compatible installed
Python >=3.12,<4, checks wheels before package installation, detects incomplete
ZIP extraction and preserves unusable existing environments with instructions.
Automatic Python installation is disabled.

The complete pinned runtime dependency set resolved to Windows x64 CPython 3.12
and 3.14 wheels, including yfinance dependencies. **Native Windows CMD execution
was not available**; the user's Windows 11 launch remains an acceptance check.
Future Python releases remain conditional on compatible dependency wheels.

## Live checks and known limits

- A bounded live Yahoo AAPL request and supported predefined-screen request were
  attempted. The cloud network proxy denied CONNECT with HTTP 403 before a usable
  Yahoo payload was returned. Nonfatal failure handling worked; live quotes and
  screen payloads are **not verified from this environment**.
- No real SEC contact is configured here. No fixture identity was sent to the
  SEC, and a fresh live full-company retrieval was **not performed**.
- Earlier release records describe three modern annual filing parsing checks
  (Apple, Microsoft, JPMorgan); those are historical, not this release's new
  live validation and not evidence of full 20-period coverage.
- Default index suggestions are the user-approved **manually maintained starter
  lists**: 35 unique tickers, incomplete and not independently verified as current
  constituent lists. The date records file maintenance, not certification.
  Optional Yahoo market screeners do not establish S&P 500/Nasdaq-100 membership.
- Scans, older plain text, nonstandard filings, predecessor CIKs, unavailable
  sources and accounting changes can leave gaps. No complete index-wide extraction
  accuracy claim, guaranteed real-time data or audited financial-history claim
  is made.
- No offline Windows product, installer, executable or permanent financial archive
  was built. A bounded working cache is retained as documented.

For an optional new live SEC acceptance check, privately configure a real
`SEC_USER_AGENT` and run `.venv/bin/python -m scripts.smoke_sec --ticker AAPL`.
Browser contact is session-only; the script does not load it or legacy settings.
Always inspect Sources & Coverage and original filings, not just test counts.
