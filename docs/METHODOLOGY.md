# Fishtorian historical methodology

The base formulas and workbook schemas are in [SPEC_v0.5.md](SPEC_v0.5.md);
new v0.6 metric definitions are in [SPEC_v0.6.md](SPEC_v0.6.md).
The workbook's Methodology and Calculation Inputs tabs record the actual
definitions and dependencies used for that company. A blank is not zero.

## Three separate layers

1. **Reported evidence:** original filing labels, tags, units, periods, accession,
   source URL, and available context, dimension and precision metadata.
2. **Explicit mappings:** narrowly defined equivalent concepts, with distinct
   ownership, revenue, cash, duration and dimensional scopes kept separate.
3. **Historical calculations:** a deterministic dependency graph shared by the
   browser and workbook. These calculations never overwrite reported statements.

Amounts are unscaled during calculation, using Decimal representations of the
retrieved numerical values; source ingestion retains the existing numeric parser.
This does not recover precision already absent from SEC APIs or previous exports.
Currency presentation uses millions; ratios use percent, multiples or days.
Unknown source precision is not invented. Denominators must be positive and above
half the source's rounding quantum, or 1e-9 when precision is unknown. Averages use
two observed balances at consecutive annual ends (300–400 days apart). Days ratios
use the actual inclusive duration of the annual revenue/cost input.

Same-period inputs must have compatible filing accessions, currencies and duration
starts. Cross-period comparisons retain both vintages and are descriptive, not
point-in-time backtests. The latest eligible comparative is not automatically a
confirmed restatement. Strict compatibility can withhold valid-but-unproven ratios.

Total revenue, net sales and customer-contract revenue are separate alternatives.
The selected analytical basis is disclosed. Gross margin additionally requires
matching revenue minus cost to reported gross profit within rounding tolerance.
Net debt currently requires an explicitly reported debt-and-finance-lease total;
it does not silently add potentially overlapping current/noncurrent debt tags.
Common ROE requires common earnings and common equity, not consolidated substitutes.
Industrial measures are withheld for unknown SICs and SIC 6000–6999. This is a
conservative gate, not a complete industry-specific analytical framework.

## v0.6: EBITDA, capital, shareholders and business drivers

EBITDA is calculated as consolidated NI + income tax expense + separately
reported interest expense + reported depreciation/depletion/amortization. First,
NI + tax must reconcile to continuing pretax income within source rounding.
This helps reject discontinued-operation/scope mismatches; it does not certify
the complete accounting classification. Other nonoperating income remains in
this definition; it is not operating income plus D&A or issuer adjusted EBITDA.
No SBC, restructuring or other discretionary addbacks are made. Its exact inputs,
reconciliation and cached formulas appear in EBITDA & Capital and Calculation Inputs.

The ROIC **proxy** uses operating income × (1 − reported effective tax rate),
divided by the two-point average of debt incl. finance leases + consolidated equity
incl. NCI − cash equivalents. A consolidated effective tax rate is not an operating
tax allocation. Deducting all cash is not estimating excess cash. The method does
not subtract investments or capitalize operating leases, nor does it implement
NOA/NFO/RNOA. It is named as a proxy in every primary view. Invalid tax rates,
nonpositive capital, missing opening balances and unsuitable industries are withheld.

Per-share growth requires exact-tag same-filing comparative observations instead
of silently joining different split vintages. EPS-minus-common-earnings growth is
only a percentage-point difference, not an exact or causal buyback decomposition.
Cash common dividends, declared common DPS, repurchase cash and authorization
balances are distinct concepts. Generic total dividends do not replace missing
common dividends in common-shareholder payout calculations.

Segment mix uses an exact recognized revenue concept matching the consolidated
denominator and source vintage. Members may overlap: displaying ratios never
establishes that they sum to 100%. Growth requires the same exact tag/axis/member
in a same-filing annual comparative; renamed members are not stitched. Acquisitions
or changed business composition can still affect growth. Operating KPIs require
reviewed exact issuer mappings with documented definitions; subscriptions, users,
devices and revenue are not interchanged.

The supplied July 2021 Morningstar Apple report motivated this metric inventory,
not source values or proprietary valuation logic. Its two differing EBITDA series
and repeated zero EV/EBITDA entries are reasons to preserve definitions and flag
unresolved data, not copy the printed numbers into this application's history.

## Research: adopted ideas versus unimplemented empirical models

| Supplied research | Application and boundary |
| --- | --- |
| Nissim & Penman (2001), *Ratio Analysis and Equity Valuation: From Research to Practice*, Review of Accounting Studies 6, 109–154 | Hierarchical definitions and separation of operating/financing concepts inform organization. No valuation, forecast, assumed tax rate or inferred excess cash. After-tax NOA/NFO/RNOA needs classification this release does not supply. |
| Fairfield & Yohn (2001), *Using Asset Turnover and Profit Margin to Forecast Changes in Profitability*, Review of Accounting Studies 6, 371–385 | Historical margin × turnover identity and arithmetic change contributions. Our pretax operating-income/average-total-assets bridge is a labelled product adaptation, not the paper's adjusted operating-asset method or forecasting regression. |
| Sloan (1996), *Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings?*, The Accounting Review 71(3), 289–315 | Compare reported earnings and operating cash flow. NI minus CFO divided by average assets is explicitly an adaptation, not replication of the paper's balance-sheet accrual construction. No persistence forecast, ranking, fraud inference or trading signal. |
| De Franco, Kothari & Verdi (March 2011 supplied manuscript), *The Benefits of Financial Statement Comparability* | Motivation for explicit comparable scopes and periods. The quarterly earnings/returns estimation procedure and peer comparability score are not implemented. |
| Debreceny, Farewell, Piechocki, Felden & Gräning (2010), *Does it add up? Early evidence on the data quality of XBRL filings to the SEC*, Journal of Accounting and Public Policy 29, 296–306 | Retain source precision and signs, test arithmetic and expose discrepancies. This release does not validate every filing calculation-linkbase relationship. |

Empirical findings in these papers are not universal thresholds or predictions
for the selected company. Original papers are user-provided research references;
they are not redistributed in the repository.

## Schedules and checks

Schedules organize reported observations and supported note disclosures. Missing
movements are not balancing plugs. No complete PP&E, equity or debt roll-forward
is claimed merely because its schedule tab exists. Segment/product/geographic
members can overlap. Contractual maturity buckets describe obligations disclosed
at an historical date, not realized payments or app-generated projections.

Structured validation checks reported assets against reported liabilities and
equity, supported beginning/change/ending cash reconciliations with distinct
restricted-cash scopes, NI-plus-tax against continuing pretax income, and the
operating-return bridge. Status is passed,
discrepancy, insufficient information, or not applicable. Legacy statement-quality
warnings remain alongside these checks. Passing does not establish an audit.

## Communication and records

CFA Institute principles concerning diligence and reasonable basis, communication
with clients, and record retention inform the evidence trail and explanations.
Fishtorian does not claim CFA certification or automatic compliance. Saved Excel
exports carry supporting records; bounded runtime caches are not a professional's
record-retention policy. Users must retain required evidence in their own workflow.
Historical ratios imply neither causation nor future performance nor investment merit.

## v0.7 compatibility repairs

An absent display override means the source value is displayed. Identical API,
inline and note representations do not become conflicts merely because one has
an explicit display override. Genuine value/sign differences still block a pair.
HTML conventional fiscal starts can use a uniquely supported structured annual
start from the same accession/end within seven days. Original observations and
the normalization reason remain available; distinct annual starts are not merged.

An unchanged amount can use its observed representation in a common filing for
analytical compatibility. Original/display values, concept, unit, dates, role and
dimensions must match. If amounts changed, the older value is not substituted.
Parent-based ROA and ROE are separately named alternatives; their availability
never establishes zero preferred equity or noncontrolling interests.

The reported effective tax rate is matching continuing-operations income tax
expense divided by pretax income. It does not require a separately tagged
consolidated NI, but still requires compatible units/vintages, positive pretax
income and a 0–100% rate. EBITDA retains the NI/tax/pretax reconciliation.
Current marketable securities can supply the specified quick-ratio investment
component; conflicting overlapping investment totals are not added.

EPS/share growth uses the latest unambiguous filing with both fiscal years.
Where that differs from the independently selected statement columns, the
Per-share Basis review discloses both representations. This is not uniform split
adjustment or verification of a corporate-action event. Filing Changes similarly
compares representations without certifying every change as a restatement.

See [release evidence and acceptance gaps](RELEASE_v0.7.md) before professional use.
