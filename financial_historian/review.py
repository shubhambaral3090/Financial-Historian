"""Visible evidence of changing reported representations; no inferred splits."""
from collections import defaultdict

from .compatibility import effective_value
from .normalization import concept_key, fallback_presentation


def per_share_basis_reviews(engine):
    from .analysis import source_datum
    from .extended_metrics import same_filing_pair
    output = []
    for row in engine.bundle.statements.get("Profit & Loss", []):
        if row.unit != "shares" and not row.unit.endswith("/shares"):
            continue
        for period, current in sorted(row.values.items()):
            previous = engine.prior(period)
            selected = row.values.get(previous)
            if selected is None:
                continue
            comparable_current, comparable = same_filing_pair(engine, source_datum(current), previous)
            if comparable.fact and (comparable.value != source_datum(selected).value
                                    or comparable_current.value != source_datum(current).value):
                output.append({
                    "Measure": row.label, "Comparison year": period, "Prior year": previous,
                    "Selected current value": effective_value(current),
                    "Common-filing current value": float(comparable_current.value),
                    "Selected prior value": effective_value(selected),
                    "Same-filing prior value": effective_value(comparable.fact), "Unit": row.unit,
                    "Selected accession": selected.accession, "Comparison accession": comparable_current.fact.accession,
                    "Selected current accession": current.accession,
                    "Selected source": selected.source_url, "Comparison source": comparable.fact.source_url,
                    "Selected current source": current.source_url,
                    "Explanation": "Different reported basis or revised amount. Do not calculate growth across the displayed columns. Same-filing growth uses the common-filing pair shown here. This does not establish a split event or a uniform adjustment factor.",
                })
    return output


def filing_changes(bundle):
    """Most recent different earlier representation of each selected cell."""
    index = defaultdict(list)
    def key(f):
        return f.statement, concept_key(f), f.unit, f.end, f.row_role, f.dimensions
    def amount(f):
        value = fallback_presentation(f)
        return f.value if value is None else value
    for fact in bundle.raw_facts:
        index[key(fact)].append(fact)
    output = []
    for statement, rows in bundle.statements.items():
        for row in rows:
            for period, selected in sorted(row.values.items()):
                earlier = [f for f in index[key(selected)]
                           if (f.filed, f.accession) < (selected.filed, selected.accession)
                           and amount(f) != amount(selected)]
                if not earlier:
                    continue
                prior = max(earlier, key=lambda f: (f.filed, f.accession))
                output.append({"Statement":statement,"Measure":row.label,"Period":period,
                               "Unit":selected.unit,"Earlier value":amount(prior),"Selected value":amount(selected),
                               "Earlier filed":prior.filed,"Selected filed":selected.filed,
                               "Earlier accession":prior.accession,"Selected accession":selected.accession,
                               "Earlier source":prior.source_url,"Selected source":selected.source_url,
                               "Explanation":"Different filed representations; may reflect reclassification, restatement, basis changes or extraction differences. Review both sources; not certified as a restatement."})
    return output
