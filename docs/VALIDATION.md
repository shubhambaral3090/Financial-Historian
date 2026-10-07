# First-version validation

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
