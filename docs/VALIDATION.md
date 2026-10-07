# Validation record


## Workbook correction and interface redesign (0.2.0)

The user-supplied complete Apple export exposed defects missed by the initial
latest-filing checks. It was compared directly with the Reliance presentation
reference. The old export split equivalent revenue/net-income rows, suppressed
available standardized figures behind partial HTML tables, lost split-cell
negative numbers, and treated a few rows in three statements as full extraction.

An offline reconstruction used the uploaded workbook's 7,157 source records and
34 filing records. No new SEC documents were fetched and no missing earlier data
was invented. The reconstructed workbook showed:

| Check | Old export | Corrected assembly |
| --- | --- | --- |
| Income statement rows | 30 | 17 |
| Populated income statement cells | 263 | 292 |
| Balance sheet rows | 83 | 43 |
| Populated balance sheet cells | 639 | 665 |
| Cash flow detail rows | 65 | 47 |
| Populated cash flow detail cells | 451 | 509 |
| Basic/diluted EPS and share counts, 2010–2016 | Missing | All 28 observations recovered |

For 2016, recovered reported diluted EPS is 8.31, investing cash flow is
-45,977 million USD, and financing cash flow is -20,890 million USD. Operating
cash flow of 66,231 million gives a net movement of -636 million, matching the
change between reported opening and closing cash. Values are sourced rather
than calculated into missing statement cells. Continuing-operation cash totals
remain separate from total-operation figures. Original XBRL outflow signs and
printed cash-flow signs remain individually traceable.

The offline reconstruction retains all original source observations. Some
standardized note/disclosure balances appear only in the Data Sheet when the
native statement does not present them; none of the previously selected native
financial monetary lines or company-specific statement lines was lost. Par value
and authorized-share descriptor facts are kept out of the main balance sheet.

The actual input cannot supply income/cash-flow figures before 2007 or balance
sheet figures before 2000. The new filing-index fallback is tested with mocked
archive records; it has not been used here to establish earlier live coverage.
Coverage checks also expose a 1 million USD disagreement in selected 2007 balance
sheet totals from different filing vintages. Historical EPS remains as reported,
with differing stock-split bases explicitly disclosed.

All 186 tests passed on both Python 3.12.14 and Python 3.14.6, with no skipped
tests. Dependency checks passed in both environments.

The light interface was exercised in Chromium at desktop and mobile widths with
an offline mocked SEC service, including first-launch contact setup, company
search/selection, progress and downloading actual Excel bytes. No fixture contact
was sent to the SEC. Streamlit AppTest covers settings/privacy, state reset,
source signs, failed retrieval and coverage-only output. These are Linux checks;
actual Windows execution and a new live full-history SEC retrieval remain unrun.

Excel generation on a synthetic 32-year / 20,160-raw-observation workload improved
from 26.29 seconds to 9.72 seconds in this environment. The smaller real uploaded
Apple dataset exported in approximately 3.9 seconds. Network retrieval time is
separate and depends on SEC responses and the local cache.

## Launcher correction and Python 3.14.6

The initial Windows launcher attempted an absent Python 3.12 and continued to
dependency installation without a usable environment on the user's machine.
The corrected launcher delegates setup to `scripts/launch_local.py` using the
default installed Python. Creation must produce a usable interpreter before
any dependency command runs. No specific absent runtime is requested.

The corrected code passed 117 tests on CPython 3.14.6, including nine setup
regressions for failed creation, false-success creation, invalid environments,
installation failure, paths with spaces and repeatable startup. A fresh real
Python 3.14.6 environment was created and prepared in a path containing spaces;
the second preparation reused it successfully. The original 108 application
tests also passed on Python 3.14.6. Windows x64 runtime wheels resolved and
downloaded successfully. Actual Windows batch execution still needs the user's
local acceptance check.

## Initial application checks

Version 0.1.0 was checked in the cloud on Python 3.12.

- `python -m pytest -q`: 108 tests passed, none skipped.
- `python -m pip check`: no broken requirements.
- Cloud setup script rerun: installation and all 108 tests passed.
- Streamlit startup and internal health request passed.
- Browser AppTest exercises first-run settings, clickable company selection,
  export, failure diagnostics, cash-flow signs and coverage-only results.
- The retrieval tests include a mocked 65-year filing inventory, every historical
  submissions shard, duplicate accessions and amendments. This demonstrates no
  configured year cap; it is not a live 65-year coverage claim.

Three actual annual SEC documents were inspected interactively and parsed:

| Issuer | Period end | Accession | Extracted observations |
| --- | --- | --- | --- |
| Apple | 2025-09-27 | 0000320193-25-000079 | 194 |
| Microsoft | 2026-06-30 | 0001193125-26-323660 | 223 |
| JPMorgan Chase | 2025-12-31 | 0001628280-26-008131 | 311 |

All three produced valid workbooks containing income statements, balance sheets,
cash flows, raw source values and provenance. Latest-period beginning cash plus
operating, investing, financing and reported exchange-rate effects reconciled
to ending cash in all three. Printed outflow signs were checked separately from
the underlying XBRL values. The checks inspected each newest filing and its
comparatives; they did not fetch complete lifetime histories.

The Windows launcher has been reviewed but could not be executed on this Linux
machine. Run it on Windows 11 for the first local acceptance check. The user
chose to enter a real SEC contact privately at first launch, so a full live
production-client history download with that identity remains unrun here.

## Optional full live check

After saving your contact in the app, run from the repository root:

```bash
python -m scripts.smoke_sec --ticker AAPL
```

This uses the saved local contact or SEC_USER_AGENT without printing it, fetches
all discoverable annual filings for that issuer and saves an XLSX in exports.
Review its Sources & Coverage; successful retrieval does not establish complete
lifetime coverage or validate every original financial line item.

## Coverage boundaries

Discovery covers the SEC submissions inventory for the chosen CIK, including
all listed historical shards. Unsupported documents, ambiguous observations,
nonannual durations and inaccessible records are explicit gaps. Some periods
use standard companyfacts fallback, which lacks custom-tag statement layout.
Untagged supported HTML retains labels and locally generated row identifiers.

Older paper reports, scanned PDFs and non-SEC archives are not automatically
searched or OCR-extracted by this first version. Pre-EDGAR and predecessor-CIK
research can require manual work. There is no fixed 10-year or 50-year cap.
