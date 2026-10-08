#!/usr/bin/env bash
set -euo pipefail
cd /workspace/Financial-Historian
python3 -c 'import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] < (4, 0) else "Python >=3.12,<4 is required")'
python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: --no-cache-dir -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
