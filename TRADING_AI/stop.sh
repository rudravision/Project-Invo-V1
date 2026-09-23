#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$ROOT/.venv/bin/python" "$ROOT/scripts/shutdown.py" --root "$ROOT"
pkill -f "streamlit run.*$ROOT" 2>/dev/null || true
echo "Stopped."
