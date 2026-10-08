# Fishtorian 0.6 — historical metric extension

This is a metric release, not a UI redesign or Morningstar data import. Annual
history remains capped at 20 periods. No forecasts, market valuation multiples,
quarterly/TTM engine, account system or permanent archive is added.

## Definitions and acceptance rules

All new calculations use the existing source dependency graph, shared browser and
Excel consumers, explicit missing reasons and unscaled calculation inputs.
Same-period inputs require matching filing vintage, duration and currency.

| Measure | Exact convention |
| --- | --- |
| EBITDA — reconciled historical definition | Consolidated net income + income tax expense + separately reported interest expense + reported depreciation/depletion/amortization. Require net income + tax to reconcile to continuing-operations pretax income; no SBC or exceptional-item addbacks. Not issuer adjusted EBITDA, operating cash flow or covenant EBITDA. |
| EBITDA margin; debt/EBITDA; EBITDA/interest | Defined EBITDA divided by revenue; explicitly reported debt incl. finance leases divided by EBITDA; EBITDA divided by separately reported interest expense. Positive denominators. |
| Debt/capital | Reported debt incl. finance leases / (that debt + consolidated equity incl. NCI). Negative equity/debt invalid; no overlapping debt sums. |
| Equity/assets | Consolidated equity incl. NCI / consolidated assets. Negative equity retained descriptively. |
| Effective tax rate | Reported income tax / positive reconciled pretax income. Only 0–100% accepted for the ROIC proxy. Not a marginal rate or operating tax allocation. |
| NOPAT proxy | Operating income × (1 − reported effective tax rate). Explicit proxy: consolidated effective tax is not necessarily the operating tax rate. |
| Invested capital proxy | Reported debt incl. finance leases + consolidated equity incl. NCI − cash equivalents. No inferred excess cash; investments and operating leases are not silently adjusted. |
| ROIC proxy | NOPAT proxy / average beginning/ending invested capital proxy. Both balances positive; consecutive annual ends. Not Morningstar ROIC, NOA/RNOA or a value-creation verdict. |
| Earnings growth | Current parent or common earnings / same-scope prior earnings − 1; positive prior, no gap. |
| Diluted EPS and weighted-share growth | Current / prior − 1 using same-filing comparative source observations, same tag/unit and annual intervals. Do not combine different split vintages. |
| EPS versus common-earnings growth gap | Difference in percentage points using same-filing comparatives for both. Descriptive, not an exact buyback attribution; diluted numerator adjustments may differ. |
| Cash common-dividend payout | ABS(cash dividends explicitly to common shareholders) / common earnings. No preferred-dividend substitution; cash timing is not declared DPS. |
| Declared DPS payout | Declared common DPS / basic EPS with matching currency-per-share units and period. Positive EPS. |
| Common repurchases / earnings | ABS(common repurchase cash) / common earnings; not a buyback yield. |
| Cash returned to common | ABS(common cash dividends) + ABS(common repurchases). Not net of issuance or authorization capacity. |
| Margin changes | Current less prior equivalent-basis gross/operating/net margin, in percentage points. |
| Segment/geographic/product mix | Recognized dimensional revenue / matching consolidated revenue concept, same vintage/period/unit. Require numerator between zero and denominator within rounding; never assume members exhaustive or additive. |
| Segment growth | Same exact tag/member/axis/unit annual comparison from the same filing; renamed/reclassified segments not silently stitched. |
| Operating KPI growth | Only approved company-CIK/exact-tag/unit/period-type mappings. Same-filing annual-end or annual-duration comparisons, no inferred ARPU, users or recurring revenue. |

Industrial EBITDA/leverage/ROIC methods are withheld for unknown or financial SICs.
Negative EBITDA remains a reported calculation, but never a leverage denominator.
Same-filing comparisons may reduce coverage; unavailable is preferable to mixing
split bases. Actual source labels/tags remain accessible even with human labels.

## Extraction and presentation

Extend curated note mappings for pretax income, tax, consolidated equity, dividends,
EPS and shares, and use the existing 21-period lookback. Operating KPIs use a local
reviewed mapping registry, initially empty: the report does not establish exact SEC
tags. Missing/unapproved KPI coverage is explicitly disclosed, not fabricated.

Add EBITDA & Capital and Operating KPIs schedules, a Business Drivers worksheet,
and learning paths for capital efficiency, per-share results and business drivers.
Keep all metric definitions, raw records, sources, blank reasons and formulas in
the existing technical sheets. Reported statement totals are untouched.

## Tests and release gates

Hand-calculated annual fixtures; EBITDA pretax reconciliation and signs; negative
earnings/denominators; incompatible currencies/vintages; tax bounds; missing opening
capital; negative equity; cash versus declared dividends; split/segment comparative
vintage; overlapping members; exact KPI registry validation; formula caches and UI
equality. Run the complete supported Python suites and desktop/mobile browser flows.
Live SEC acceptance remains separate and requires privately configured real contact.

These definitions are internally consistent with the historical-only scope. ROIC
is explicitly a limited proxy, not the full operating/financing framework deferred
in v0.5. Unsupported proprietary KPIs and definitions stay unavailable.
