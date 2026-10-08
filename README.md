# Fishtorian

A private, browser-based historical financial research workspace. Select a company
to automatically load Yahoo market context, SEC annual statements, supporting
schedules, historical calculations, explanations and a matching Excel workbook.
Then choose **Download Excel workbook**.

Version 0.6 presents up to **20 fiscal periods**, with 52 defined historical
measures plus supported business-driver calculations. This is a research starting
point, not a certified database, valuation model, or investment recommendation.
Institutional acceptance remains pending independent live-filing verification.
See [release evidence](docs/RELEASE_v0.6.md), [metric specification](docs/SPEC_v0.6.md),
[research methodology](docs/METHODOLOGY.md), and the
[fictional example workbook](docs/examples/Fishtorian_Example.xlsx).

The Fishtorian wordmark is surrounded by two opposing Pisces-inspired fish.
The GitHub repository and internal Python package keep their existing names.

## Start the web app on Windows 11

1. Use an installed Python **>=3.12 and <4**. The release is tested on Python
   3.12, 3.13 and 3.14.6. Install Python yourself if no compatible runtime exists.
2. Download the repository ZIP and choose **Extract All**. Keep all files together;
   do not launch inside the ZIP or copy only the command file.
3. Double-click **launch_windows.cmd**. First launch creates a private environment,
   checks dependency-wheel availability, and installs pinned packages over secure
   PyPI connections. Keep its window open while using the web app.
4. Enter your real name/organization and email in the centered contact dialog.
   SEC automated-access policy requires identifying contact information. No API
   key, password, subscription or payment is needed.
5. Search by ticker, company name or CIK, or click a sidebar suggestion. Everything
   loads automatically; download the workbook when ready.

The Windows command only starts the browser web app; it is not an offline
application, installer or executable. The server binds to loopback. Closing the
launcher stops it; closing just the browser does not. Refresh the browser tab for
a new data check.

The launcher accepts compatible newer Python 3.x and discovers installed
alternatives when the default is too old. It never silently installs Python.
Future versions may lack dependency wheels; preflight explains a tested fallback.
An incompatible existing `.venv` is preserved with recovery instructions. Do not
disable certificate checks. Native Windows execution remains a local acceptance
check; automated runtime tests and Windows x64 wheel checks were run from Linux.

## Suggestions and Yahoo market data

The default source is [config/ticker_groups.json](config/ticker_groups.json):
**35 manually maintained starter tickers**, grouped under S&P 500 and Nasdaq-100.
These lists are explicitly **incomplete and not independently verified**. Their
maintenance date is not a claim of current membership certification. The user
approved this fallback because yfinance does not provide verified predefined
constituent screeners for these indexes. Nasdaq-listed is not Nasdaq-100.

Edit that file to maintain or expand your list. See its schema and the provider's
`ManualUniverseProvider(config_path=...)` for custom paths. Each browser page session
shuffles cached members locally; randomizing suggestions makes no Yahoo universe
request. Direct SEC search is not restricted to these starter lists. No Wikipedia
or arbitrary membership-page scraping is used.

Optional Yahoo screeners can be configured centrally using the JSON environment
variable `FINANCIAL_HISTORIAN_YAHOO_SCREENERS`, for example:

```json
[{"id":"most_actives","label":"Most active"}]
```

These are general Yahoo market-universe suggestions, not verified index
constituents. Successful lists have a 12-hour cache and bounded last-good fallback
(seven days maximum) with original timestamps and warnings. Failed requests use
a five-minute cooldown. No universe failure blocks direct SEC search.

Yahoo Finance through `yfinance` supplies latest available daily prices and
historical charts. The UI shows price date, exchange timezone when provided,
currency, retrieval time and stale-cache status. Current-day daily bars are
labeled delayed; quotes are not guaranteed real-time. Missing prices/charts never
block SEC financial statements. The market provider interface is separate from
SEC extraction and can be replaced later.

## Financial history and Excel

The SEC is authoritative. Annual filing metadata is discovered through all listed
submissions shards; supported documents are retrieved for a bounded 21-period
window, allowing a lookback balance or recovery of a misleading metadata date.
Presentation stays limited to 20 annual ends. Older metadata and raw structured facts remain auditable. The app
does not retrieve every company's financial history or build a permanent archive.

Workbook layout follows the supplied Reliance reference's compact annual columns.
Historical calculations use this project's explicit definitions:

- **Profit & Loss, Balance Sheet, Cash Flow:** reported sections and bold totals.
  Cash Flow is a compact reported-total overview; **Cash Flow Detail** matches the
  full cash-flow preview online.
- **Data Sheet:** column A contains reported line items; B:U contain up to 20
  fiscal dates, oldest to newest. Three vertical statement blocks keep it clean.
- **Source Data:** 21 technical columns retain original tags, labels, units,
  unscaled values, period dates, accession, filed date, form, extraction, selection
  reason, source URL, displayed-cell coordinates, presentation value, original
  instant, row role, section, context ID, dimensions and source decimals when supplied. Older raw facts remain here.
- **Sources & Coverage / Read Me:** 20-period policy, blanks, omitted/unsupported
  data, selection rules, warnings and original source links.
- **Supporting schedules:** Revenue & Segments, Working Capital, Debt &
  Liquidity, Capital & PP&E, Earnings & Cash, Equity & Shares, EBITDA & Capital,
  and Operating KPIs. These group
  supported reported observations; they do not invent complete roll-forwards.
- **Historical Ratios / Return Bridge / Common Size:** descriptive calculations
  from compatible inputs. No future columns, recommendations or composite scores.
- **Business Drivers:** supported same-filing segment/KPI growth and matching
  consolidated-revenue shares; members are not assumed exhaustive or additive.
- **Methodology / Calculation Inputs / Validation:** definitions, an inspectable
  dependency graph, source evidence, and passed/discrepancy/insufficient-information/
  not-applicable checks.

Each populated reported statement cell has a source link and provenance comment.
Calculated cells link through formulas and comments to Calculation Inputs. Browser
and export share one selected dataset, periods, units, signs and warnings.
Currency values use millions; per-share figures and share counts retain reported
units. Source Data preserves original XBRL signs separately from printed signs.
Excel formulas include cached results for data-only readers. Excel recalculation
is enabled; editing formulas or inputs requires a compatible spreadsheet application.

### Historical analysis and learning

Overview, Statements, Schedules, Metrics & learning, and Sources & checks provide
progressively deeper views. Guided paths explain profitability, cash generation,
working capital, debt, capital efficiency, per-share results and business drivers.
Each metric has a formula, interpretation limitations,
company-specific worked inputs, and filing evidence.

Version 0.6 adds reconciled EBITDA and margin, debt/EBITDA and EBITDA/interest,
debt/capital and equity/assets, effective tax, an explicitly labelled ROIC proxy,
earnings/EPS/share-count changes, dividend payout measures, cash repurchases and
common distributions, and margin changes in percentage points. No Morningstar
figures or proprietary definitions are imported. EBITDA is not cash flow or
covenant EBITDA. ROIC uses a reported-effective-tax and all-cash-deducted capital
proxy; it is not a precise operating-tax allocation or a reproduction of Morningstar.

EPS/share-count and segment growth require same-filing comparative evidence.
Missing common-dividend, consolidated-equity, pretax, D&A or debt-total facts can
leave new measures unavailable even when other financial data is present. The
app does not treat absent preferred/minority interests, investments or debt as zero.

Operating-KPI support is configuration-driven, **not automatic universal coverage**.
The reviewed registry [config/operating_kpis.json](config/operating_kpis.json) starts
empty: no real-issuer tag mapping was verified in this release. Administrators can
add exact CIK/tag/unit/period definitions only after source review. See
[KPI mapping instructions](docs/OPERATING_KPIS.md). Invalid configuration skips KPIs
with a coverage note and does not block financial retrieval. No user/device counts,
ARPU or recurring revenue are inferred from prose.

Industrial-company methods require a known nonfinancial SEC SIC. Unknown SICs,
financial firms, missing components, unlike currencies, differing duration starts,
conflicting same-period filing vintages and unsuitable denominators can make a
metric unavailable. The reason appears online and in the workbook cell comment.

Total revenue, net sales and customer-contract revenue remain distinct. Growth
requires a consistent basis. A wholly unsupported metadata date less than 120 days
from an observed annual end is excluded by an explicitly documented heuristic;
coverage keeps the original record. Genuine missing annual years remain visible.

Annual inline note support includes curated PP&E, interest, common equity/income,
debt/maturity concepts, and explicitly dimensional business-segment, product and
geographic facts. Supported standard note facts can also come from companyfacts.
Members may overlap and must not be summed blindly. Maturities are contractual
as-of disclosures. Arbitrary custom debt notes, scanned reports, complete PP&E/debt
roll-forwards, and full after-tax NOA/NFO/RNOA classification are not implemented.
Their absence is not treated as zero. No assumed marginal tax rates or excess-cash
adjustments are introduced. Historical common-size and return bridges are labelled
product adaptations, not replications of the papers' empirical models.

Only genuinely equivalent concepts align. Current/noncurrent and continuing/total
operations stay separate. Missing values stay blank, not zero; even wholly empty
selected periods remain visible with explanations. No missing totals are invented.

Structured SEC history is strongest from around 2009. Earlier supported HTML can
be parsed, but old plain text, scans, inaccessible documents, predecessor CIKs and
unusual layouts can require manual research. Latest eligible annual comparatives
are favored; that alone does not establish a restatement. Historical EPS/share
counts are not uniformly split-adjusted. Reconciliation checks detect some
problems, not every defect. Review coverage and filings before preparing a model.

## Automatic refresh, caches and contact privacy

Company selection starts one workflow with independent Yahoo and SEC loading.
Progress reports statement retrieval and workbook preparation; a ready workbook can download even while
market loading continues. Ordinary widget reruns/downloads do not regenerate the
page. Browser refresh restores non-secret selected CIK/ticker URL parameters and
checks providers again. Last-good fallback has its original timestamps and a
warning; a new dataset never receives a mismatched older workbook.

Contact stays in this tab's `sessionStorage` and server-session memory. It is sent
only in SEC request headers, not to Yahoo, URLs, logs, diagnostics or Excel. It is
not written to project files or retained in a global service cache. Browser
session-restore settings may retain tab storage after reopening. If session
storage is disabled, a full refresh asks again. Legacy `data/settings.json` is
neither read nor overwritten; remove an old contact file yourself if unwanted.

Working caches are bounded, not a permanent financial-data archive:

- Public SEC responses: 250 MB disk cache in ignored `data/cache`.
- Quotes: at most 128 cached entries, five-minute freshness, up to 24-hour stale
  fallback, plus request pacing and failure cooldowns.
- Financial results: at most eight in-memory bundle/workbook pairs, 64 MiB total,
  expiring after 24 hours; no contact-bearing service objects stored there.

`data`, `logs`, `exports` and `.venv` remain outside Git. Excel files are saved
when you choose to download. Diagnostics use event names, versions and timestamps,
not raw exceptions or contact values.

## Development and cloud setup

Use the existing checkout, not a separate worktree. With Python >=3.12,<4:

```bash
bash scripts/setup_cloud.sh
.venv/bin/python -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true
```

The setup script installs development dependencies, checks them and runs the
offline suite. On Windows, use `.venv\Scripts\python.exe -m pytest -q` after
installing `requirements-dev.txt`; the launcher installs runtime packages only.
See [the metric specification](docs/SPEC_v0.6.md) and
[release validation evidence](docs/RELEASE_v0.6.md) for tested versus blocked capabilities.

Network hosts include `www.sec.gov`, `data.sec.gov`, PyPI package hosts,
`query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `fc.yahoo.com`,
`finance.yahoo.com`, `consent.yahoo.com` and `guce.yahoo.com`. Hosted/corporate
networks may deny providers independently; keep TLS verification enabled.

For an optional live SEC check, privately configure `SEC_USER_AGENT` with a real
name/email, then run `.venv/bin/python -m scripts.smoke_sec --ticker AAPL`. This
does not read browser contact or legacy settings. Never put real identity in
fixtures, shell transcripts, screenshots or GitHub.
