# Fishtorian 0.5 — release evidence

Validation date: 2026-10-08. **Institutional acceptance pending.**

This release implements the historical research layer, not a forecast model,
account system, hosted deployment, offline application or verified index database.
The earlier version's evidence remains in [VALIDATION.md](VALIDATION.md).

## Delivered phases

1. Accounting, workbook and UX specification, including exact formula and source
   fields: [SPEC_v0.5.md](SPEC_v0.5.md).
2. Revenue-scope repair; WMT custom/standard duplicate handling; explained
   unsupported metadata-date exclusion; 21-period internal lookback; preserved
   context/dimension/precision metadata.
3. Six historical schedules, with supported annual note and dimensional facts
   separate from consolidated statements. Incomplete roll-forwards stay incomplete.
4. Thirty core historical measures and bridge components, common-size statements,
   compatible-input checks, invalid-denominator rules and sector applicability.
5. Fishtorian Pisces-inspired identity and Overview, Statements, Schedules,
   Metrics & learning, Sources & checks views. Four guided learning paths, exact
   tables, source links, worked inputs, historical chart gaps, automatic export.
6. Statement/Data Sheet layout retained; new schedule, ratio, bridge, methodology,
   calculation-input and validation tabs. Inspectable formulas with numeric caches.
7. Regression/runtime/browser testing, reproducible example and release docs.

## Evidence categories

### Live-tested

- Yahoo AAPL request returned a quote and 251 historical daily points. Retrieval
  timestamp: 2026-10-08T03:03:43Z. Quote was labelled latest available close,
  not real-time. This is one provider smoke check, not availability certification.
- GitHub read access succeeded using the configured platform authentication.
  The final handoff separately identifies whether the release push succeeded.

### Fixture-tested / mocked

- Full pytest suite: **417 passed** on each of Python **3.12.14**,
  **3.13.5** and **3.14.6**. No skipped tests or failures.
  Provider failure, privacy, automatic loading,
  refresh, cache, launcher, mapping and export tests remain active.
- Independently specified, hand-calculated four-year fictional dataset verifies
  24 exact expected metrics plus bridge identity, missing/invalid inputs,
  same-period vintage and currency mismatches, applicability and opening balances.
- Real Chromium journeys at 1440×1100 and 390×844: search, automatic download,
  session-contact refresh, no page overflow, 20-period default fixture, and a
  separate rich fixture exercising schedules, teaching views and a 15% operating
  margin identical to the cached Excel value. Network providers were replaced
  with fictional fixtures; this is not a live-company browser acceptance test.
- Excel formula cells, cached numeric results, source links, text-injection safety,
  unavailable explanations and workbook/browser alignment are tested.
- Legacy WMT export replay exercises its source records without another network
  request. Presentation is 20 annual January ends (2007–2026), not the extra empty
  April 2009 metadata date. Distinct total revenue and net sales remain separate;
  same-value native custom duplicates consolidate. This is regression evidence
  from the user's prior output, not independent verification of Walmart's filings.
- The supplied Reliance workbook informed the compact annual matrix, statement
  blocks and separation of technical source data. It is a layout reference, not
  an accounting mapping for US companies. The earlier Apple output was inspected
  for layout/coverage differences; its 34-period technical export predates the
  current 20-period presentation.

### Unsupported by design or implementation limits

- Full after-tax NOA/NFO/RNOA, operating/financing tax allocation, empirical peer
  comparability scoring, original Sloan replication, and industrial ratios for
  banks/insurers or unknown SICs.
- Arbitrary custom debt-note schemas, scanned reports and exhaustive roll-forwards.
  Company-specific face-statement lines remain available; note extraction is
  deliberately narrower. Segment members are not assumed exhaustive or additive.
- Uniform split-adjustment of historical per-share data, automatic predecessor-CIK
  stitching, guaranteed twenty years for every company, and certified memberships.
- Forecasts, recommendations, account creation and social login are out of scope.

### Blocked / unverified

- Independent SEC filing acceptance: no private real SEC contact was configured.
  No identity was invented. Configure SEC_USER_AGENT privately or enter a contact
  in the browser. The live smoke command verifies retrieval, but does not by itself
  complete the independent manual comparison below.
- GOOG's reported thirteen-year result has no supplied artifact in this task;
  predecessor-CIK or parser causes are not established. Do not claim it repaired.
- Actual Windows 11 launcher execution, native Excel/LibreOffice recalculation and
  exhaustive keyboard/screen-reader auditing were not run in this Linux cloud.
  Browser layout and programmatic XLSX checks are not substitutes for those checks.
- Future Python versions remain conditional on compatible dependency builds.

## Institutional acceptance still required

Use WMT, AAPL, GOOG, an industrial company and a bank/insurer as an initial manual
sample. Select recent, earlier and changed-definition years. Independently open
the original filings, record accession/context/unit, and compare revenue, earnings,
cash, assets, debt, equity and selected note disclosures. Hand-recalculate supported
ratios, average balances, cash reconciliation and return contributions. Investigate
every discrepancy and scope change; unsupported cases must remain explained blanks.
Verify identical browser/workbook facts, cached values and recalculated formulas
in native Excel. Record reviewer, date, sample and unresolved issues. Broader
coverage is not proven by those five companies alone. Until this evidence exists,
the product is an auditable research starting point, not a certified database.

## Reproduce

```bash
.venv/bin/python -m pytest -q
.venv/bin/python tests/browser_smoke.py --chromium /usr/bin/chromium --output /tmp/fishtorian-browser
.venv/bin/python tests/browser_smoke.py --rich --chromium /usr/bin/chromium --output /tmp/fishtorian-rich-browser
.venv/bin/python -m pip check
```

Browser smoke testing additionally needs Playwright and an installed Chromium;
neither is a runtime requirement for users. The committed
[example workbook](examples/Fishtorian_Example.xlsx) uses only a clearly fictional
teaching company. It is generated by the production exporter, not a hand-designed
mock spreadsheet. See [methodology](METHODOLOGY.md) for research adaptations.
