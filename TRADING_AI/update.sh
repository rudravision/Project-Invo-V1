#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P="$ROOT/.venv/bin/python"
"$P" -m pip install --upgrade -r "$ROOT/requirements.txt"
"$P" "$ROOT/scripts/probe_sources.py"
"$P" "$ROOT/scripts/bootstrap_data.py" --root "$ROOT" --yes
"$P" "$ROOT/scripts/run_pipeline.py" --root "$ROOT"
