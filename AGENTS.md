# Financial Historian

Use the existing checkout. Normal development does not need a Git worktree.

This is a private local Windows application with a Streamlit browser interface.
Use `.venv/bin/python` in the cloud workspace and install `requirements-dev.txt`
for development. Run `python -m pytest` before delivering extraction changes.

Financial correctness matters more than filling cells. Preserve original units,
company-specific tags, source dates and filing URLs. Do not fabricate missing
observations or combine overlapping concepts into invented statement totals.
Keep printed statement signs separate from source/XBRL concept signs. Every
selected figure needs source provenance; later comparatives are not necessarily
confirmed restatements. Report unsupported periods and formats explicitly.

There is no user-requested year cap. Read every historical SEC submissions shard;
do not truncate history for convenience. SEC discovery is not lifetime coverage.
Do not add forecasts, valuations, analyst adjustments or investment conclusions.

SEC networking needs a real contact configured locally by the user or through
SEC_USER_AGENT. Never print it, hardcode an identity, disable TLS verification,
or treat a missing contact as a missing API key. Use the rate-limited client.
Automated tests use mocked data; optional live tests require private contact
configuration. Avoid exposing localhost preview links in onboarding reports.

Keep local settings, caches, exports and logs ignored by Git and out of release
ZIPs. The Windows launcher must remain beginner-friendly and bind to loopback.
