#!/usr/bin/env bash
set -euo pipefail
cd /workspace/Financial-Historian
python3 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
