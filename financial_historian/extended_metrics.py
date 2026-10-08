"""Explicit historical definitions; never a provider's opaque adjusted EBITDA."""
from decimal import Decimal


def definitions(make):
    items = [
        ("ebitda", "EBITDA — reconciled historical definition", "Earnings bridge", "Consolidated NI + tax + interest + reported D&A", "currency", "Earnings before specified financing, tax and depreciation/depletion/amortization charges.", "Requires NI + tax to reconcile to continuing pretax income. No SBC/exceptional addbacks; not cash flow or covenant EBITDA.", True),
        ("ebitda_margin", "EBITDA margin — reconciled definition", "Earnings bridge", "Defined EBITDA / revenue", "%", "Specified EBITDA per unit of revenue.", "Inherits the reconciled EBITDA definition; not operating cash generation.", True),
        ("debt_ebitda", "Reported debt incl. finance leases / EBITDA", "Debt", "Reported debt including finance leases / defined EBITDA", "x", "Borrowing relative to the defined annual earnings measure.", "Positive EBITDA required; not years of cash repayment or a covenant calculation.", True),
        ("ebitda_interest", "EBITDA / interest expense", "Debt", "Defined EBITDA / separately reported interest expense", "x", "Earnings-based coverage of interest expense.", "Excludes principal repayments and capex; not comprehensive debt-service coverage.", True),
        ("debt_capital", "Debt / capital — including NCI", "Debt", "Debt / (debt + consolidated equity including NCI)", "%", "Borrowings as a share of the defined book-capital base.", "Requires reported debt including finance leases and nonnegative consolidated equity; no overlapping debt sums.", True),
        ("equity_assets", "Consolidated equity / assets", "Capital efficiency", "Equity including NCI / total assets", "%", "The book-equity share of the asset base.", "Negative equity is retained; this is not a market-value capital structure.", False),
        ("effective_tax", "Effective tax rate — reconciled", "Capital efficiency", "Income tax expense / continuing pretax income", "%", "Historical effective tax rate supporting the labelled ROIC proxy.", "Requires positive pretax income, 0–100% tax rate and NI/tax reconciliation. Not a marginal or operating tax rate.", True),
        ("nopat_proxy", "After-tax operating income — ETR proxy", "Capital efficiency", "Operating income × (1 − reported effective tax rate)", "currency", "Operating profit after a clearly specified historical tax proxy.", "Consolidated effective tax is not necessarily the operating tax allocation; not reported NOPAT.", True),
        ("invested_capital_proxy", "Invested capital — cash-deducted proxy", "Capital efficiency", "Debt including finance leases + equity including NCI − cash equivalents", "currency", "A reproducible book-capital denominator for the ROIC proxy.", "Deducts all cash, not estimated excess cash. No silent investment or operating-lease adjustments; requires positive capital.", True),
        ("roic_proxy", "ROIC — effective-tax, cash-deducted proxy", "Capital efficiency", "After-tax operating income proxy / average invested capital proxy", "%", "Historical operating return on a defined average book-capital base.", "Not Morningstar ROIC or after-tax RNOA. Two-point averages; consolidated ETR and all-cash deduction are explicit approximations.", True),
        ("parent_earnings_growth", "Parent earnings growth", "Shareholder analysis", "Parent NI / prior equivalent parent NI − 1", "%", "Historical change in parent-company earnings.", "Positive prior earnings required; do not confuse earnings growth with EPS growth.", False),
        ("common_earnings_growth", "Common earnings growth — same filing", "Shareholder analysis", "Common earnings / same-filing prior common earnings − 1", "%", "Common-shareholder earnings growth on an identified comparative basis.", "Requires explicit common earnings and a same-filing comparative; not substituted with consolidated income.", False),
        ("diluted_eps_growth", "Diluted EPS growth — same filing", "Shareholder analysis", "Diluted EPS / same-filing prior diluted EPS − 1", "%", "Historical per-share earnings growth.", "Same-filing comparatives reduce split-vintage mismatch; positive prior EPS required. Diluted numerator adjustments may differ from basic earnings.", False),
        ("diluted_shares_growth", "Diluted weighted shares change — same filing", "Shareholder analysis", "Diluted weighted shares / same-filing prior shares − 1", "%", "Change in the annual diluted weighted-average share denominator.", "Not period-end shares or an exact buyback attribution. A same-filing split-comparable basis is required.", False),
        ("eps_earnings_gap", "EPS versus common-earnings growth gap", "Shareholder analysis", "Diluted EPS growth − common earnings growth", "pp", "Separates growth in per-share results from growth in common earnings.", "Descriptive gap, not a causal or exact repurchase decomposition; diluted earnings adjustments also matter.", False),
        ("cash_dividend_payout", "Cash common-dividend payout", "Shareholder analysis", "ABS(common cash dividends) / common earnings", "%", "Cash dividends to common shareholders relative to their positive earnings.", "Cash timing differs from declaration dates; preferred dividends are not included.", False),
        ("declared_dps_payout", "Declared common DPS / basic EPS", "Shareholder analysis", "Declared common dividends per share / basic EPS", "%", "Declared common per-share distributions relative to positive basic EPS.", "Declared rather than paid dividends; exact currency-per-share units must match.", False),
        ("repurchase_earnings", "Common repurchase cash / common earnings", "Shareholder analysis", "ABS(common repurchase cash) / common earnings", "%", "Repurchase spending relative to positive common earnings.", "Not repurchase authorization, buyback yield or net reduction in shares.", False),
        ("common_cash_returned", "Cash returned to common shareholders", "Shareholder analysis", "ABS(common cash dividends) + ABS(common repurchase cash)", "currency", "Actual cash dividends plus common-share repurchases.", "Not net of new issuance, and not an authorization balance or shareholder total return.", False),
    ]
    for base, label in (("gross_margin", "Gross"), ("operating_margin", "Operating"), ("net_margin", "Parent net")):
        items.append((base + "_change", label + " margin change", "Profitability", "Current margin − prior equivalent-basis margin", "pp", "Historical percentage-point change in profitability.", "Not percentage growth or a claim about causes; numerator and revenue scopes must remain comparable.", base != "net_margin"))
    return [make(*row) for row in items]


def calculate(engine, d, p):
    from .analysis import combine, currency, equivalent, missing, quantum, source_datum
    def get(key):
        item = engine.get(key, p)
        valid_unit = (item.unit == "shares" if key == "shares_diluted" else
                      item.unit.endswith("/shares") and currency(item.unit.split("/")[0])
                      if key in {"eps_basic", "eps_diluted", "declared_common_dps"} else currency(item.unit))
        if item.value is not None and not valid_unit:
            return missing(item.label, p, "Reported unit is incompatible with this metric's input definition.", item.unit)
        return item

    def calc(formula, args, fn, denom=None, label=None, unit=None):
        unit = unit or d.unit
        if unit == "currency":
            unit = next((f.unit for a in args for f in a.sources if currency(f.unit)), "currency")
        return combine(label or d.label, p, unit, formula, tuple(args), fn, denom)

    def blocked(reason, args=()):
        # Preserve failed inputs in the workbook dependency graph as well.
        from .analysis import Datum
        return Datum(d.label, p, d.unit, inputs=tuple(args), reason=reason)

    def ratio(a, b):
        if a.value is not None and b.value is not None and a.unit != b.unit:
            return blocked("Ratio inputs have incompatible reported units.", (a, b))
        return calc("{0}/{1}", (a, b), lambda x, y: x/y, b)

    def pretax_check():
        a, b, c = get("net_income_total"), get("tax_total"), get("pretax_continuing")
        check = calc("{0}+{1}-{2}", (a, b, c), lambda x, y, z: x+y-z, unit="currency")
        tolerance = sum((quantum(f)/2 for f in check.sources), Decimal("0.000001"))
        if check.value is None:
            return check.reason
        if abs(check.value) > tolerance:
            return "Consolidated NI + income tax does not reconcile to continuing pretax income; discontinued/equity-method scopes may differ."
        return ""

    key = d.key
    if key in {"ebitda", "effective_tax"}:
        problem = pretax_check()
        base = (get("net_income_total"), get("tax_total"), get("pretax_continuing"))
        if problem:
            return blocked(problem, base)
        if key == "effective_tax":
            result = ratio(base[1], base[2])
            if result.value is not None and not 0 <= result.value <= 1:
                return blocked("Effective tax rate is outside 0–100%; no normalized tax rate is assumed.", (result,))
            return result
        interest, da = get("interest"), get("da_total")
        if any(a.value is not None and a.value < 0 for a in (interest, da)):
            return blocked("Negative interest or D&A cannot be treated as an EBITDA addback.", (*base, interest, da))
        # Pretax reconciliation is retained as an explicit zero-valued dependency.
        check = calc("{0}+{1}-{2}", base, lambda x,y,z:x+y-z, unit="currency", label="NI plus tax less pretax reconciliation")
        return calc("{0}+{1}+{2}+{3}+0*{4}", (base[0], base[1], interest, da, check), lambda a,b,c,e,check:a+b+c+e)
    if key == "ebitda_margin":
        return ratio(engine.metric("ebitda", p), engine.revenue(p))
    if key == "debt_ebitda":
        debt = get("debt_total")
        if debt.value is not None and debt.value < 0:
            return blocked("Reported debt cannot be negative for this leverage definition.", (debt,))
        return ratio(debt, engine.metric("ebitda", p))
    if key == "ebitda_interest":
        return ratio(engine.metric("ebitda", p), get("interest"))
    if key == "equity_assets":
        return ratio(get("consolidated_equity"), get("assets"))
    if key in {"debt_capital", "invested_capital_proxy"}:
        debt, equity = get("debt_total"), get("consolidated_equity")
        if any(a.value is not None and a.value < 0 for a in (debt, equity)):
            return blocked("Negative debt or equity is unsuitable for this capital definition.", (debt, equity))
        if key == "debt_capital":
            capital = calc("{0}+{1}", (debt, equity), lambda x,y:x+y, unit="currency", label="Debt plus consolidated equity")
            return ratio(debt, capital)
        cash = get("cash")
        result = calc("{0}+{1}-{2}", (debt, equity, cash), lambda x,y,z:x+y-z)
        if cash.value is not None and cash.value < 0 or result.value is not None and result.value <= 0:
            return blocked("Cash must be nonnegative and invested capital must be positive; no balancing adjustment is made.", (result,))
        return result
    if key == "nopat_proxy":
        return calc("{0}*(1-{1})", (get("operating_income"), engine.metric("effective_tax", p)), lambda x,y:x*(1-y))
    if key == "roic_proxy":
        previous = engine.prior(p)
        if not previous:
            return blocked("A consecutive opening invested-capital balance is required.")
        a, b = engine.metric("invested_capital_proxy", previous), engine.metric("invested_capital_proxy", p)
        capital = calc("({0}+{1})/2", (a, b), lambda x,y:(x+y)/2, unit="currency", label="Average cash-deducted invested capital proxy")
        return ratio(engine.metric("nopat_proxy", p), capital)
    if key in {"cash_dividend_payout", "repurchase_earnings", "common_cash_returned"}:
        dividend, repurchase, earnings = get("common_dividend_cash"), get("repurchases"), get("common_income")
        if key == "common_cash_returned":
            return calc("ABS({0})+ABS({1})", (dividend, repurchase), lambda x,y:abs(x)+abs(y))
        value = dividend if key == "cash_dividend_payout" else repurchase
        return calc("ABS({0})/{1}", (value, earnings), lambda x,y:abs(x)/y, earnings)
    if key == "declared_dps_payout":
        a, b = get("declared_common_dps"), get("eps_basic")
        if a.value is not None and b.value is not None and (a.unit != b.unit or not a.unit.endswith("/shares")):
            return blocked("DPS and EPS must have identical currency-per-share units.", (a, b))
        if a.value is not None and a.value < 0:
            return blocked("Negative declared dividends are not a supported payout numerator.", (a,))
        return ratio(a, b)
    if key == "eps_earnings_gap":
        return calc("{0}-{1}", (engine.metric("diluted_eps_growth", p), engine.metric("common_earnings_growth", p)), lambda x,y:x-y)
    growth_inputs = {"parent_earnings_growth":"net_income", "common_earnings_growth":"common_income", "diluted_eps_growth":"eps_diluted", "diluted_shares_growth":"shares_diluted"}
    if key in growth_inputs:
        current = get(growth_inputs[key])
        if key == "diluted_shares_growth" and current.value is not None and current.value <= 0:
            return blocked("Current weighted-average shares must be positive.", (current,))
        previous = engine.prior(p)
        if not previous:
            return blocked("A consecutive prior annual observation is required.", (current,))
        if key == "parent_earnings_growth":
            prior = engine.get(growth_inputs[key], previous)
        else:
            prior = same_filing_prior(engine, current, previous)
        if current.value is not None and prior.value is not None and not equivalent(current, prior):
            return blocked("Growth inputs have different accounting scopes or units.", (current, prior))
        return calc("{0}/{1}-1", (current, prior), lambda x,y:x/y-1, prior)
    if key.endswith("_margin_change"):
        base_key = key.removesuffix("_change")
        previous = engine.prior(p)
        if not previous:
            return blocked("Consecutive annual margins are required.")
        current, prior = engine.metric(base_key, p), engine.metric(base_key, previous)
        if current.value is not None and prior.value is not None:
            # The actual numerator and denominator used by each margin must align.
            if len(current.inputs) != 2 or len(prior.inputs) != 2 or not all(equivalent(a,b) for a,b in zip(current.inputs, prior.inputs)):
                return blocked("Margin numerator or revenue basis changed across periods.", (current, prior))
        return calc("{0}-{1}", (current, prior), lambda x,y:x-y)
    raise KeyError(key)


def same_filing_prior(engine, current, previous):
    """Do not infer split or segment comparability from different filing vintages."""
    from .analysis import missing, source_datum
    if not current.fact:
        return missing(current.label, previous, "Current source observation is unavailable.", current.unit)
    f = current.fact
    candidates = [x for x in (*engine.selected, *engine.bundle.raw_facts, *engine.bundle.disclosures)
                  if x.end == previous and x.accession == f.accession and x.tag == f.tag
                  and x.unit == f.unit and x.dimensions == f.dimensions
                  and x.row_role == f.row_role and (x.start is None) == (f.start is None)]
    if not candidates or len({(x.value,x.start,x.presentation_value) for x in candidates}) != 1:
        return missing(current.label, previous, "An unambiguous same-filing comparative is required; split or definition bases are not assumed.", current.unit)
    return source_datum(max(candidates, key=lambda x: (bool(x.context_id), bool(x.decimals))))
