# Fishtorian

Use the existing checkout. Normal development does not need a Git worktree.

This is a private browser-based Streamlit web application. The Windows command
only starts the web server; do not build an offline app or installer.
Use `.venv/bin/python` in the cloud workspace and install `requirements-dev.txt`
for development. Run `python -m pytest` before delivering extraction changes.

Financial correctness matters more than filling cells. Preserve original units,
company-specific tags, source dates and filing URLs. Do not fabricate missing
observations or combine overlapping concepts into invented statement totals.
Keep printed statement signs separate from source/XBRL concept signs. Every
selected figure needs source provenance; later comparatives are not necessarily
confirmed restatements. Report unsupported periods and formats explicitly.

Present the latest 20 fiscal periods, with the same selected bundle in the browser
and Excel. Read SEC submissions shards for discovery, but limit document retrieval
to 21 periods (20 displayed plus beginning-balance/metadata lookback). Preserve raw
source facts and explain omitted periods.
SEC discovery is not lifetime coverage. Suggestion groups are manually maintained,
dated and explicitly incomplete; do not claim certified current index membership.
Do not add forecasts, valuations, analyst adjustments or investment conclusions.
Documented historical calculations belong in the separate analysis dependency
graph, not in reported statements. Browser and Excel must use that same graph.
Missing or incompatible inputs produce explained blanks. Do not call this release
institutional grade before independent live-filing acceptance in docs/RELEASE_v0.6.md.
Keep the v0.6 ROIC proxy explicitly labelled; do not imply actual operating tax
allocation, inferred excess cash, or Morningstar replication. EBITDA requires its
pretax reconciliation. Per-share/segment growth requires same-filing comparisons.
Operating KPI mappings require exact issuer/tag/unit/period evidence; the default
registry is empty. Do not manufacture mappings or substitute loosely named facts.

SEC networking needs a real contact entered in the tab session or through
SEC_USER_AGENT. Never print it, hardcode an identity, disable TLS verification,
or treat a missing contact as a missing API key. Use the rate-limited client.
Automated tests use mocked data; optional live tests require private contact
configuration. Avoid exposing localhost preview links in onboarding reports.

Never persist entered contact to project files or a global service cache.
Keep legacy local settings, caches, exports and logs ignored by Git and out of release
ZIPs. The Windows launcher must remain beginner-friendly and bind to loopback.
