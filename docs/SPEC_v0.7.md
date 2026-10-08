# v0.7 reliability repair specification

## Evidence and acceptance

The user supplied v0.6 Apple (2006–2025) and Cisco (2007–2026) exports.
They are regression evidence, not independent verification of SEC filings.
Before repair, 27/52 and 28/52 defined metrics have any observations;
17/22 and 16/22 v0.6 additions are entirely blank. Validation has 36/64
and 19/81 passed/insufficient checks respectively. Availability is not accuracy.

Acceptance checks cover the actual exported observations, including Apple 2016
revenue 215,639m and operating income 60,024m, Apple 2025/2024 diluted EPS
7.46/6.08, Cisco 2026/2025 diluted EPS 3.33/2.55, and Cisco 2018 receivables
5,554m. Preserve uploads and generate separate reviewed replay outputs.

## Phase 1: source and accounting compatibility

- Optional display metadata must not turn numerically identical same-filing
  facts into a conflict. Preserve real sign, value, scope and unit conflicts.
- Reconcile conventional HTML annual starts to uniquely supported same-filing
  structured periods; retain originals and the evidence for the reconciliation.
- Suppress redundant fallback revenue and receivables rows only with explicit
  equivalence evidence. Preserve total versus component revenue distinctions.
- Add verified spelling variants for interest tags; analytical expense magnitude
  uses source concept signs while statement presentation retains printed signs.
- For cross-filing calculations, accept unchanged values only with an observed
  common filing representation. Never simply remove vintage checks or substitute
  a changed figure silently. Use a coherent evidence basis for average balances.
- Recognize short-term marketable securities for the defined quick ratio with
  explicit ambiguity checks. Keep consolidated, parent and common scopes distinct;
  provide separately named parent-return alternatives when common/consolidated
  evidence is unavailable. Do not infer absent preferred stock or NCI as zero.
- Compute the reported effective tax rate from matching tax/pretax inputs;
  its mathematical definition does not require a missing alternative NI tag.
- Keep unknown debt/lease totals, tax allocations and operating KPIs unavailable.

## Phase 2: presentation and coverage

- Prominent per-share basis warnings and a basis-review schedule compare selected
  historical EPS/shares with same-filing comparatives. Do not claim uniform split
  adjustment or infer corporate actions from price changes.
- Make original/later representations reviewable without claiming every revision
  is a restatement. Keep source URLs, dates, units and original labels.
- Group statement sections consistently and remove technical deprecation text
  from display labels while preserving original labels/tags in source records.
- Diagnose missing ending cash with parser regressions; never invent ending cash
  as beginning cash plus movements. Distinguish annual and transition coverage.
- Retain unsupported periods explicitly; replace the broad 120-day date heuristic
  with evidence about invalid metadata rather than temporal proximity alone.

## Phase 3: responsiveness

- Cache public parsed filing facts by document fingerprint, accession, parser
  version and KPI configuration. Bound retention and size; no permanent archive.
- Reuse successful company results within a short freshness window on selection;
  browser reload still checks for updates. Keep last-good fallback timestamps.
- Deliver statements before Excel finishes, reuse one analysis graph for both,
  cache statement HTML and isolate research-widget reruns from provider loading
  and sidebar charts. Research tabs may still render together within that view.
- Add contact-safe stage durations and exception-class diagnostics.

## Phase 4: verification and delivery

Run extraction/accounting/cache regressions, complete suites on available Python
3.12/3.13/3.14.6, browser checks, and replay both uploaded exports. Inspect formulas,
cached results, provenance and visible warning treatment. Document exact remaining
gaps and any lack of independent live SEC verification. Update launch/release
instructions, commit and push to the existing repository. No offline app, accounts,
forecasts, new data provider, or institutional-grade claim.

## Consistency review

Reported facts remain separate from derived schedules. Both browser and Excel use
the same prepared bundle and analysis. New evidence may permit a calculation;
absence of evidence never becomes zero. Replays cannot repair facts that were
never extracted, so parser fixes also require document-level tests. Bounded caches
contain public filing data only; session contacts remain isolated.
