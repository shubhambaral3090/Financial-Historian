# Fishtorian v0.7 — reliability repairs

Validation date: 2026-10-08. This release repairs problems reproduced from the
user's v0.6 Apple and Cisco exports. Replaying those exports checks extraction
selection, accounting calculations and presentation; it does **not** independently
establish that the original exports match every SEC filing. Institutional
acceptance remains pending.

## What changed

- Identical API, inline and note observations no longer conflict solely because
  one omits an optional display override. Genuine value/sign conflicts remain.
- Conventional HTML fiscal starts can be reconciled to a unique structured annual
  start in the same filing, within seven days. Raw observations remain available.
- Calculations can use an unchanged amount's actual representation in a common
  filing. Original/display values, statement, accounting concept, units, period,
  role and dimensions must match; vintage checks are not removed.
- Dated receivables labels align without merging different accounting scopes.
  Statement sections group consistently; display labels omit technical
  deprecation suffixes while source records preserve them.
- Correct interest-tag spelling and source expense signs restore supported
  coverage calculations. Current marketable securities can supply the defined
  quick-ratio component, subject to overlap checks. Interest-only and combined
  interest-and-dividend income remain distinct statement lines.
- Reported effective tax requires compatible continuing-operations tax and
  pretax inputs, positive pretax income and a 0–100% rate. EBITDA still requires
  its separate NI/tax/pretax reconciliation.
- Two explicitly named parent-return alternatives bring the static library from
  52 to 54 measures. Parent earnings/assets is not consolidated ROA; parent ROE
  is not common ROE. Missing preferred equity or NCI is never assumed zero.
- Per-share growth can use the latest actual filing containing both years.
  **Per-share Basis** exposes differing displayed and comparison values;
  **Filing Changes** makes changed filed representations reviewable. Neither
  schedule certifies a split event or restatement.
- Unsupported short periods remain visible. A filing-day metadata date is
  excluded only with contradictory report-end observations in that accession.
  Cash ending-label recognition includes “end of fiscal year”.

## Results from the two supplied workbooks

The original uploads were preserved. Separate outputs were generated under
`/tmp` and are not committed as independently verified financial examples.

| Replay measure | Apple v0.6 | Apple v0.7 | Cisco v0.6 | Cisco v0.7 |
| --- | ---: | ---: | ---: | ---: |
| Presented fiscal periods | 20 | 20 | 20 | 20 |
| Defined static measures | 52 | 54 | 52 | 54 |
| Measures with at least one value | 27 | 35 | 28 | 34 |
| Populated static metric/period cells | 295 | 588 | 266 | 501 |
| Reconciliation checks passed | 36 | 53 | 19 | 30 |
| Checks with insufficient information | 64 | 47 | 81 | 70 |
| Periods with working-capital day measures | 2 | 18 | 2 | 15 |

Availability is not an accuracy score. The larger metric-cell count includes
the two new, separately defined parent-return measures. Apple has eight
per-share basis-review records in the final replay; Cisco has none. Absence of
a record does not establish that every historical basis is comparable.

Specific regression expectations include:

- Apple 2016: revenue 215,639m and operating income 60,024m support a 27.8354%
  operating margin once the same-filing HTML start-date conflict is resolved.
- Apple 2025 versus 2024: diluted EPS 7.46 / 6.08 − 1 = 22.6974%; diluted
  weighted shares 15,004,697,000 / 15,408,095,000 − 1 = −2.6181%.
- Cisco 2026 versus 2025: diluted EPS 3.33 / 2.55 − 1 = 30.5882%; diluted
  weighted shares 3,987,000,000 / 3,998,000,000 − 1 = −0.2751%.
- Cisco 2018 net receivables of 5,554m no longer require duplicate rows for
  changing allowance/date labels.

The two replays each checked all **1,080 static metric/period Excel cached cells**
against the prepared analysis, including explained blanks, percentages,
percentage points and currency scaling. This is browser/export consistency
evidence; regression expectations and scope tests provide separate math checks.
Run `python -m scripts.check_replay --help` for the reusable check.

## Responsiveness and privacy

Sourced statement previews appear before analysis and workbook generation finish.
The final browser view and workbook reuse one prepared calculation graph.
Research widgets run in a Streamlit fragment, and statement HTML has a bounded
24-entry rendering cache. Tabs within the fragment may still render together.
Interactive fragments initialize at one stable root location; this also fixes
the blank mobile/tab-reset failure found during browser testing. Temporary
previews have their own cleared placeholder so they do not remain alongside
the finished statements.

Selecting a recent company can reuse its successful result for five minutes.
A full browser reload rechecks providers; fallback retains original timestamps
and warnings. Parsed public filing facts use JSON, keyed by document fingerprint,
filing metadata, parser version and KPI configuration, with a seven-day TTL,
64 MiB total limit and 16 MiB entry limit. This supplements existing bounded
caches; it is not a permanent archive. Contact information is not stored there.

Safe diagnostics record stage durations and sanitized exception classes, never
provider exception text or contact information. In the final replay run, Apple
analysis/loading took 5.15 seconds and workbook generation 22.62 seconds; Cisco
took 5.42 and 26.76 seconds respectively. These include concurrent test activity,
exclude network retrieval, and are not a guaranteed end-to-end latency or a
before/after performance benchmark.

## Verification and limits

The complete suite passes **503 tests, no skips**, on each of Python **3.12.14**,
**3.13.5** and **3.14.6**. Dependency consistency passes with unchanged pinned
requirements. Tests exercise scope/vintage/sign conflicts, unchanged common
filing evidence, annual date ambiguity, 52/53-week day counts, cash labels,
cache expiry/corruption/size, automatic refresh, progressive event order, formula
caches and contact privacy.

Both Chromium browser modes pass at **1440×1100** and **390×844**. These launch
the real Streamlit app with fictional SEC/Yahoo providers. They check automatic
loading, contact isolation, refresh, export, selected research tabs, historical
analysis, chart rendering and page overflow. Provider-failure and chart-fallback
regressions run separately in the automated suite. These are not live provider
acceptance. The fictional example workbook was regenerated through the
production exporter, including the new review worksheets.

Remaining limits:

- No independent live SEC acceptance was possible: a real SEC identity is not
  privately configured. Attempts to reach official issuer investor-relations
  sources also failed at the network layer. No fresh live Yahoo claim is made.
- Debt totals, consolidated/common earnings and equity, D&A and payout scopes
  can still be insufficient. Several EBITDA, ROIC, debt and distribution metrics
  remain blank in both replays. They were not filled with inferred totals.
- Cisco's supplied source records lack ending cash. The parser-label repair has
  document-fixture coverage; replay cannot recover a fact absent from its input.
- EPS/share statement columns remain as reported, not uniformly split-adjusted.
  Review the comparison basis before using them in another model.
- The operating-KPI registry remains empty. The manually maintained ticker
  suggestions remain incomplete and are not certified index constituents.
- Native Windows 11 launch, native Excel/LibreOffice recalculation, comprehensive
  accessibility review and the earlier GOOG history issue remain unverified.
- Historic scans/plain text, arbitrary custom notes, complete roll-forwards and
  full NOA/NFO/RNOA classification remain unsupported. This is historical research
  preparation, not forecasting, valuation or an audited financial database.

## Obtain and run

Download the committed GitHub repository ZIP, choose **Extract All** into a new
folder, then launch `launch_windows.cmd`. It starts the browser app and selects
a compatible installed Python; it does not install another Python silently.
No new dependency or cloud setup migration is needed for v0.7.

See [README](../README.md), [repair specification](SPEC_v0.7.md),
[methodology](METHODOLOGY.md) and the regenerated
[fictional example](examples/Fishtorian_Example.xlsx).
