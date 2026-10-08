"""Bounded rendering cache for public, immutable statement cells."""
from functools import lru_cache
import html

from .export import CURRENCIES, _safe_source_url


def statement_html(bundle, statement):
    rows=tuple((r.label,r.unit,r.section,r.is_total,tuple(sorted(r.values.items())))
               for r in bundle.statements.get(statement,[]))
    return _render(statement,tuple(sorted(bundle.periods)),rows)


@lru_cache(maxsize=24)
def _render(statement, periods, rows):
    columns="".join(f"<th scope='col'>{html.escape(p)}</th>" for p in periods)
    body=[]
    previous_section=""
    for label,unit,section,is_total,items in rows:
        if section and section!=previous_section:
            body.append(f"<tr class='statement-section'><th scope='row'>{html.escape(section)}</th><td colspan='{len(periods)+1}'></td></tr>")
            previous_section=section
        monetary=unit in CURRENCIES
        display_unit=f"{unit} million" if monetary else unit
        values=dict(items)
        cells=[]
        for p in periods:
            fact=values.get(p)
            if fact is None:
                cells.append("<td class='missing' aria-label='Unavailable'>—</td>")
                continue
            value=fact.presentation_value if fact.presentation_value is not None else fact.value
            value=value/1000000 if monetary else value
            number=f"{abs(value):,.6f}".rstrip("0").rstrip(".")
            text=f"({number})" if value<0 else number
            if _safe_source_url(fact.source_url):
                source=html.escape(fact.source_url,quote=True)
                cells.append(f"<td><a href='{source}' target='_blank' rel='noopener noreferrer' title='Open SEC source'>{text}</a></td>")
            else:
                cells.append(f"<td>{text}</td>")
        emphasis=" class='statement-total'" if is_total else ""
        body.append(f"<tr{emphasis}><th scope='row'>{html.escape(label)}</th><td class='unit'>{html.escape(display_unit)}</td>{''.join(cells)}</tr>")
    return (f"<div class='statement-preview' tabindex='0' role='region' aria-label='{html.escape(statement)} annual history'>"
            f"<table><thead><tr><th scope='col'>Line item</th><th scope='col'>Unit</th>{columns}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")
