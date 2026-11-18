#!/usr/bin/env bash
# Rebuild the SAMPLE database and start the pilot dashboard on http://127.0.0.1:8765
set -e; cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv; .venv/bin/pip install -q -r requirements.txt; }
.venv/bin/python gen_sample.py
.venv/bin/python -m pp.demo --seed
exec .venv/bin/uvicorn app:app --host 127.0.0.1 --port "${PORT:-8765}"
