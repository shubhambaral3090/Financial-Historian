# Financial Historian v0.4 technical specification

## Scope and consistency check

Browser-based, private research workspace; no offline application, installer,
valuation model, or permanent financial archive. Selecting a company starts one
pipeline. Its only normal follow-up action is **Download Excel workbook**.

The installed yfinance predefined screens do **not** provide verified S&P 500 or
Nasdaq-100 constituent lists. Nasdaq exchange listings are not Nasdaq-100
membership. The user approved manually maintained ticker groups instead. The
default JSON contains 35 explicitly incomplete starter tickers with a maintenance
date, not certified current index membership. Optional genuine Yahoo screens
remain centrally configurable and labeled as general market suggestions.

The remaining requirements are consistent: the browser and workbook consume the
same limited StatementBundle, provider errors are independent, and the source
facts may cover more periods than the presentation. Cache timestamps never mean
live prices or complete financial coverage.

## Pipeline and refresh

1. Recover this tab's SEC contact from browser session storage or request it in a
   centered first-launch dialog. Validate name/email; keep no project-file copy.
   The service is session-owned, never globally cached with a contact key.
2. Resolve the selection to SEC company/CIK; reject invalid/mismatched identifiers.
   Load Yahoo market context independently so SEC failure does not hide prices.
3. Discover SEC annual filings, retrieve supported documents for the latest 20
   fiscal periods, preserve structured raw facts, and expose coverage gaps.
4. Limit the assembled statements once, then render that exact bundle and build
   its workbook. New financial data must never download an older workbook.
5. Use one progress indicator and show provider-specific results as they arrive.
   A normal widget rerun/download does not fetch again. Full browser refresh
   restores the non-secret selected CIK/ticker from the URL and rechecks sources.

Manual ticker groups are loaded locally with a maintenance date and no Yahoo
universe requests. Optional Yahoo successes have a 12-hour cache, bounded stale fallback and failure
cooldown. Shuffle only cached members, once per browser page session. Market
quotes use bounded success-only caching, rate limiting and stale fallback.
Financial fallback stores a bounded, expiring in-memory bundle/workbook pair, not
contacts or an archive. SEC response files retain the existing 250 MB bounded
cache. Each section shows retrieval time; workbook generation has its own time.

## Exact Excel Data Sheet layout (defined before implementation)

**Data Sheet:** column A is the reported line item. Columns B through U are up to
20 ISO fiscal period-end dates, oldest to newest. Repeat the date header for each
vertical Profit & Loss, Balance Sheet and full Cash Flow block. Reported sections
and totals retain their formatting. Currency amounts use millions; other units
are explicit in the label/section. Missing values remain blank. Source comments
and links are attached to each populated financial cell. No derived ratios,
invented totals or projection columns are introduced.

**Source Data:** technical provenance moves out of the clean matrix. Its exact
columns A:R are: Statement; SEC tag / row id; Reported label; Reported unit;
Source value (unscaled); Annual period start; Annual period end; Accession;
Filed; Form; Extraction; Selection reason; Source filing URL; Displayed cells;
Presentation value; Original source instant; Row role; Reported section.

Statement tabs share these selected values, signs, source links, units and the
same 20-period window. Sources & Coverage explains omitted periods, unsupported
formats, partial extraction and reconciliation warnings. Raw source facts remain
available in Source Data even when outside the presentation window. Export
rejects an unbounded bundle instead of silently producing a different window.

## Privacy and interface

Light responsive layout; no permanent contact panel or manual provider-refresh
buttons. Sidebar cards contain Yahoo names/tickers and, when available, price,
movement, timestamp and sparkline. Direct search follows the same pipeline.
Contact is used only for SEC headers and this tab's session, not Yahoo, logs,
exports or diagnostics. Public UI errors are fixed safe explanations, never raw
exceptions. Contact information is not in URLs. Browser session storage clears
with the tab (browser session-restore behavior is controlled by the browser).

## Tested delivery phases

1. Configurable Yahoo universe, successful-cache fallback and local shuffling.
2. Automatic orchestration, independent failures, session contact and progress.
3. SEC validation, 20-period integration and matching clean Excel matrix.
4. Offline regression suite; mocked desktop/mobile browser workflows; bounded
   live-provider checks where permitted; Python 3.12, 3.13 and 3.14.6 checks;
   dependency wheel preflight; documentation, GitHub and cloud setup update.

The Windows command remains only a launcher for the browser web app. Select an
installed compatible Python >=3.12,<4, preflight pinned dependency wheels, never
silently install Python, and explain the tested fallback if builds are missing.
Live, fixture-tested, blocked and unverified behavior must be reported separately.
