# Reviewed historical operating KPIs

The release ships an empty `config/operating_kpis.json` registry. There are no
verified real-company mappings bundled with v0.6. The extraction and calculation
path is fixture-tested, not a claim of subscriber/device coverage for Apple.

An administrator must inspect an actual SEC annual filing before adding a mapping.
Match the issuer CIK, exact namespaced tag, source unit, instant versus annual
duration, and definition. A subscriber is not necessarily a unique person. Record
the evidence URL and review date. Do not add contact information to this registry.

The schema is `{"schema_version": 1, "mappings": [...]}`. Each mapping requires:

| Field | Meaning |
| --- | --- |
| cik | Ten-digit issuer CIK, as a string |
| tag | Exact namespaced XBRL tag, not a fuzzy label or guessed local name |
| label | Human-readable reviewed metric name |
| unit | Exact parsed source unit, e.g. `pure` for a count when confirmed |
| period_type | `instant` at an annual reporting end or `annual` duration |
| definition | Scope, population, basis and interpretation limitations |
| source_url | HTTPS SEC Archives evidence for that same issuer |
| verified_on | ISO review date, YYYY-MM-DD |

The registry validator checks structure, duplicates, issuer URL and required
fields, not the truth of an administrator's interpretation. It does not fetch
the evidence URL. Human filing verification remains essential. Restart the app
after changing the registry so in-memory financial-result caches cannot mask it.

Extraction is limited to supported inline tagged annual filings. The original
reported label/tag, dimensions, context, precision and unit remain in Source Data.
The reviewed definition/evidence is recorded in the selection explanation and
shown in the business-driver learning view. Growth needs a consecutive,
unambiguous same-filing comparative with the same tag, dimensions and unit.
There is no prose extraction, inferred ARPU, device-to-customer conversion, or
automatic taxonomy mapping. A changed definition must be reviewed before reuse.

Invalid/unreadable registry configuration produces a nonfatal coverage note.
No mapping or no compatible observation means no KPI value, never zero. Standard
SEC statement retrieval and Yahoo quotes are independent of KPI coverage.
