"""Evidence-based compatibility without overwriting original reported facts."""
from collections import defaultdict
from dataclasses import replace
from datetime import date

from .models import Fact
from .normalization import concept_key


def effective_value(fact: Fact):
    return fact.value if fact.presentation_value is None else fact.presentation_value


def reconcile_html_periods(facts: list[Fact]) -> list[Fact]:
    """Replace conventional HTML starts only with a unique reported annual start.

    Callers retain the input facts as audit records. All structured observations
    for the same accession/end must agree; quarterly durations cannot qualify.
    """
    starts = defaultdict(set)
    for fact in facts:
        if fact.extraction == "html-table" or not fact.start or fact.row_role:
            continue
        days = (date.fromisoformat(fact.end) - date.fromisoformat(fact.start)).days + 1
        if 300 <= days <= 400:
            starts[fact.accession, fact.end].add(fact.start)
    result = []
    for fact in facts:
        candidates = starts[fact.accession, fact.end]
        if fact.extraction == "html-table" and fact.start and len(candidates) == 1:
            actual = next(iter(candidates))
            if abs((date.fromisoformat(actual) - date.fromisoformat(fact.start)).days) <= 7:
                note = (f"Annual start verified from unique structured annual contexts in the same filing: {actual}. "
                        f"Original HTML convention: {fact.start}.")
                if "Annual start verified" not in fact.selection_reason:
                    fact = replace(fact, start=actual, selection_reason=fact.selection_reason + " " + note)
        result.append(fact)
    return result


def common_filing_observations(selected: list[Fact], observations: list[Fact]) -> list[Fact]:
    """Find a common filing that actually reports the selected amounts.

    Per end date, choose the filing reproducing most selected observations.
    Each replacement requires the same concept, original amount, displayed
    amount, unit, period, role and dimensions. Changed amounts never substitute.
    Unmatched observations retain their filing and still fail compatibility.
    """
    def identity(f):
        return (f.statement, concept_key(f), f.value, effective_value(f), f.unit, f.start,
                f.end, f.row_role, f.dimensions)

    index = defaultdict(list)
    for fact in observations:
        index[identity(fact)].append(fact)
    by_end = defaultdict(list)
    for fact in selected:
        by_end[fact.end].append(fact)
    output = []
    for end, facts in by_end.items():
        coverage = defaultdict(set)
        for fact in facts:
            for candidate in index[identity(fact)]:
                coverage[candidate.filed, candidate.accession].add(identity(fact))
        anchor = max(coverage, key=lambda v: (len(coverage[v]), v), default=None)
        for fact in facts:
            candidates = [f for f in index[identity(fact)] if (f.filed, f.accession) == anchor]
            if candidates and anchor != (fact.filed, fact.accession):
                found = max(candidates, key=lambda f: (bool(f.context_id), bool(f.decimals)))
                fact = replace(found, selection_reason=found.selection_reason +
                               " Unchanged amount verified in a common filing for calculation compatibility; "
                               f"statement selection remains {fact.accession}.")
            output.append(fact)
    return output
