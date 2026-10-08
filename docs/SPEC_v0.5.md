# Fishtorian 0.5 — historical analysis specification

## Scope and consistency

Private browser application; annual reported history and descriptive calculations;
no projections, valuations, advice, accounts, hosting, or permanent archive.
Existing retrieval, session contact, cache and market boundaries remain. Derived
analysis is explicitly authorized by the new brief; reported figures stay intact.

All consumers use the validated 20-period presentation and the same deterministic
analysis engine. Raw source facts remain available. A missing value is not zero.
“Institutional grade” is an acceptance gate, not an asserted certification.

## Observed baseline

v0.4 has source records, automatic provider loading, statement export and basic
reconciliation. It merges Revenues, SalesRevenueNet and customer-contract revenue;
the WMT export splits those aliases by tag and duplicates custom net sales. The
WMT file contains an empty 2009-04-01 column among January fiscal ends. The earlier
AAPL export has 34 periods and raw technical Data Sheet rows; it predates the
current 20-period matrix. Current extraction discards dimensional contexts and
notes. No GOOG artifact is supplied: predecessor/CIK or source limitations remain
unverified, not established causes. No real SEC contact is configured for live tests.

## Selection and provenance

Separate total revenue, net sales and customer-contract revenue. Only exact
curated custom labels may identify a standard concept, with period/value
confirmation required before deduplication. Unknown concepts retain source labels.
Retain contexts, dimensions and decimals when provided by inline/instance XBRL.
Dimensional disclosures are separate from consolidated statement rows.

Choose at most 20 annual ends. Genuine unsupported years remain visible. An
unobserved, unsupported metadata date within 120 days of an observed annual end
is excluded with a coverage explanation; this is a documented heuristic, not a
claimed correction of SEC metadata. Retain a bounded extra retrieval period for
opening balances and selection recovery. Do not silently join predecessor CIKs.

Use selected statement observations for analysis. Lookback observations outside
the display window are allowed for beginning balances. Preserve their provenance.
Ambiguous inputs, unlike currencies, conflicting duration starts and conflicting
same-period filing vintages prevent a calculation. Cross-year changes disclose
their source vintages. Annual differences/averages require consecutive annual ends.

## Exact analytical definitions

Currency amounts are computed unscaled, displayed in millions. Ratios are
fractions internally; days are actual inclusive annual duration days. Two-point
averages use beginning and ending balances. Near-zero denominators use disclosed
source precision where available, otherwise a documented numerical guard.

| Measure | Formula / input convention |
| --- | --- |
| Revenue growth | current / prior equivalent revenue − 1; positive prior |
| 3-year revenue CAGR | (current / value three annual intervals earlier)^(1/3) − 1; positive endpoints, complete consecutive series |
| Gross margin | gross profit / matching sales; verify revenue − cost of sales = gross profit before admitting basis |
| Operating margin | operating income / selected revenue; state revenue basis |
| Parent net margin | parent net income / selected revenue; explicit parent earnings scope |
| SG&A, R&D intensity | respective expense / selected revenue |
| Capex intensity | magnitude of reported PP&E cash purchases / selected revenue |
| Consolidated ROA | consolidated net income / average total assets |
| Common ROE | explicitly common-shareholder income / average explicitly common equity |
| Current ratio | current assets / current liabilities |
| Quick ratio (strict) | (cash + explicitly short-term investments + net trade receivables) / current liabilities; all required, no absent-as-zero |
| Reported borrowing components | separately identified current and noncurrent borrowings; never sum overlapping categories |
| Net debt | explicitly reported total debt − cash equivalents; excludes restricted cash and investments |
| Debt/assets | explicitly reported total debt / total assets |
| Operating income/interest | reported operating income / separately reported interest expense; identified as operating coverage, not covenant EBITDA coverage |
| Receivable days | average net trade receivables / matching sales × actual days; all-credit-sales proxy |
| Inventory days | average inventory / cost of sales × actual days |
| Payable days | average trade payables / cost of sales × actual days; purchases proxy |
| Cash conversion cycle | receivable days + inventory days − payable days |
| OCF margin | total operating cash flow / selected revenue |
| Earnings cash conversion | total OCF / consolidated net income; positive earnings required |
| OCF less capex | total OCF − magnitude of PP&E purchases; not an intrinsic value or standardized free cash flow |
| Earnings–cash difference | consolidated net income − total OCF; not original Sloan accrual replication |
| Asset-scaled earnings–cash difference | preceding difference / average assets |
| Asset turnover | selected revenue / average assets |
| Operating return on total assets | operating income / average total assets; pretax, not Nissim–Penman RNOA |
| Return change bridge | prior turnover × Δoperating margin + prior margin × Δturnover + Δmargin × Δturnover |

Common-size P&L uses the disclosed revenue basis; balance sheet uses total assets.
Never divide EPS or share counts by revenue. Ratios needing industrial-company
interpretation are withheld for financial firms (SIC 6000–6999) or unknown SIC.
Negative/zero denominators and incomplete periods have explicit unavailable reasons.
Historical losses themselves are retained; they are not deleted as research outliers.

Advanced NOA/NFO/after-tax RNOA require complete, documented operating/financing
classification and tax allocation. No automatic excess-cash, tax-rate or adjustment
assumptions. Unsupported advanced measures receive explicit explanations. Fairfield
and Nissim use different definitions; the implemented total-assets bridge is labelled
as an adaptation of their algebra, not a replication of either empirical method.

## Schedules and evidence

Six schedules group selected reported rows without manufacturing roll-forwards:
Revenue & Segments; Working Capital; Debt & Liquidity; Capital & PP&E;
Earnings & Cash; Equity & Shares. Include recognized annual note facts separately,
and dimensional segment facts with explicit axis/member, unit, scope and vintage.
Do not infer that dimensional members are exhaustive or additive. Debt maturity
disclosures retain their as-of date and contractual bucket, not realized payments.
Unretrieved components and unsupported complete reconciliations are disclosed.

## UI and workbook prototype

Brand: Fishtorian centered, two opposing Pisces-inspired fish around the name.
Light ink/teal palette. Wordmark on welcome/header; compact emblem on small screens.

Company page: profile/market → Historical overview → Statements → Schedules →
Metrics & learning → Sources & checks. Progressive disclosure; automatic preparation.
Each metric offers a formula, purpose, company-specific calculation, inputs/source
links, reason if unavailable, and interpretation limitations. Guided paths cover
profitability, earnings/cash, working capital and debt. Historical charts retain gaps.

Workbook preserves existing statement/Data Sheet layout: A = row label, B:U =
annual periods, chronological; dark column headers, teal section bands, bold totals,
currency millions, parentheses for negatives, blanks for missing.
Additional tabs: six schedules; Historical Ratios; Return Bridge; Common Size;
Methodology; Calculation Inputs; Validation. Sources remain separate.

Exact Methodology columns: Metric; Group; Formula; Unit; Purpose; Applicability;
Balance convention; Limitations; Reference.
Exact Calculation Inputs columns: ID; Description; Period; Unit; Value / formula;
Status; Explanation; Source tag; Original label; Accession; Filed; Source URL;
Context; Dimensions; Source decimals.
Exact Validation columns: Period; Check; Status; Difference; Tolerance; Explanation.
Source Data adds Context; Dimensions; Decimals after the existing 18 fields.

Formula dependencies reference Calculation Inputs, with computed cached results
stored in XLSX for readers that do not recalculate. Excel automatic recalculation
remains enabled. Source text is never executable Excel content. No external links.
Every missing derived cell has a comment explaining its omission.

## Acceptance gates

1. Deterministic unit/regression evidence for scopes, conflicts, dates, denominator
rules, dimensions, privacy, formula math and lineage; full existing suite retained.
2. Independent hand calculations for a multi-year fixture, explicit expected
ratios and a reconciled change bridge; currency and scope rejection cases.
3. Parse supplied WMT source records to exercise regression cases without claiming
that a prior app export is independent authoritative filing verification.
4. XLSX formulas and cached values match the same analysis object rendered online.
5. Desktop/mobile browser journeys, source access, explanations, and download.
6. Run installed supported runtimes; distinguish actual runs from dependency checks.
7. Live source comparison where privately configured contact and network permit.
If live independent comparisons are blocked, label institutional acceptance pending.
Never promote fixture-only success to a claim of audited company coverage.
