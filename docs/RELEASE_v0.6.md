# Fishtorian v0.6 — historical metric release

Validation date: 2026-10-08. Institutional acceptance remains pending independent
live-filing review. This release extends metrics, not the application style or
scope into forecasts, valuation recommendations, quarterly/TTM data or accounts.

## Delivered

- 22 additional defined historical measures, taking the static library from 30
  to 52; supported segment/KPI observations generate additional business-driver rows.
- Reconciled EBITDA, margin, debt/EBITDA, interest coverage, debt/capital and
  equity/assets. Explicit NI-plus-tax/pretax validation with source precision.
- Effective tax, after-tax operating-income proxy, cash-deducted invested capital
  and average-capital ROIC proxy. No assumed marginal tax rates or excess cash.
- Earnings/EPS/weighted-share growth, descriptive EPS/earnings growth gap, cash
  common-dividend payout, declared-DPS payout, repurchases/earnings, cash returned
  to common shareholders and margin changes in percentage points.
- Same-filing dimensional revenue growth, matching-concept revenue shares, and
  reviewed operating-KPI extraction/growth infrastructure.
- Shared UI/Excel formulas and sources, three additional learning paths, additional
  chart choices, EBITDA & Capital and Operating KPIs schedules, Business Drivers tab.
- Persistent tab selection: changing learning-path controls no longer resets the
  selected research tab during a Streamlit rerun.

## Accounting acceptance examples

The fixture is a fictional teaching company, not reconstructed Apple accounts.
Hand-specified latest-year inputs include revenue 1,200m, consolidated NI 120m,
tax 30m, pretax income 150m, interest 12m, D&A 30m, debt 180m, consolidated equity
620m, cash 60m and operating income 180m. Opening defined capital is 610m.

| Independently calculated expectation | Result |
| --- | --- |
| EBITDA: 120 + 30 + 12 + 30 | 192m |
| EBITDA margin: 192 / 1,200 | 16% |
| Debt / EBITDA: 180 / 192 | 0.9375× |
| EBITDA / interest: 192 / 12 | 16× |
| Debt / capital: 180 / (180 + 620) | 22.5% |
| Defined closing capital: 180 + 620 − 60 | 740m |
| NOPAT proxy: 180 × (1 − 30/150) | 144m |
| ROIC proxy: 144 / average(610,740) | 21.3333…% |
| Common cash dividends 20m + repurchases 40m | 60m |
| Diluted weighted shares: 80m / 100m − 1 | −20% |
| Segment revenue: 600m / 400m − 1; 600m / 1,200m | 50% growth; 50% share |

## Verification and limits

The full suite passes **481 tests, with no skips**, on each of Python **3.12.14**,
**3.13.5** and **3.14.6**. Dependency consistency passes with unchanged
pinned requirements. No setup/dependency migration is required.

Both real Chromium browser modes pass at 1440×1100 and 390×844. The baseline mode
checks the 20-period export, automatic loading, contact isolation and browser
refresh. The richer mode checks the new capital/shareholder/business-driver paths,
preserved active tab after selection, 21.33% displayed ROIC matching Excel's cached
144/675 result, no page overflow and the added worksheets. Providers are fictional
fixtures, not live Yahoo/SEC calls. Initial browser tests exposed the tab-reset issue;
it was fixed and both modes rerun successfully.

Tests cover scope/currency/vintage mismatches, negative/near-zero denominators,
invalid tax rates, negative equity, missing D&A, cash versus declared dividends,
common versus total dividends, split-vintage requirements, member renames,
unavailable opening balances, source lineage and formula-cache agreement.

No independent live SEC acceptance occurred: SEC_USER_AGENT is not privately
configured in this environment. New financial methods and KPI extraction are
fixture-tested. No Morningstar financial values, ratings or forecasts are imported.
No fresh live Yahoo claim is made for this metric-only release; provider code is
unchanged and existing provider-failure/privacy regressions remain in the suite.

Important limits:

- ROIC is the named historical proxy, not Morningstar ROIC or full NOA/NFO/RNOA.
- The KPI registry is initially empty. Real-company subscription/device coverage
  requires source-reviewed mappings; generic prose extraction is not implemented.
- Strict consolidated-equity, common-earnings, debt-total and same-filing requirements
  can leave metrics unavailable even when some financial statements are populated.
- Segment reorganization, acquisitions and issuer-definition changes still require
  review; identical names do not prove economic comparability.
- Native Windows 11 launch, native Excel/LibreOffice recalculation, comprehensive
  accessibility review and the unresolved GOOG history issue remain unverified.

For institutional acceptance, continue the independent issuer/year/filing checks
specified in [v0.5 release evidence](RELEASE_v0.5.md), adding NI/tax/pretax, D&A,
interest, consolidated equity, debt, common payouts and same-filing comparatives.
Review each proxy definition before use; passing fixture math is not a financial audit.

## Obtain and run

Use the committed repository ZIP, extract all files into a new folder and launch
`launch_windows.cmd`. No new Python dependency or runtime installation is required
beyond the existing pinned environment. The cloud setup/startup workflow is unchanged.
The regenerated fictional example is `docs/examples/Fishtorian_Example.xlsx`.
See [SPEC_v0.6.md](SPEC_v0.6.md), [METHODOLOGY.md](METHODOLOGY.md) and
[OPERATING_KPIS.md](OPERATING_KPIS.md) for definitions and coverage requirements.
