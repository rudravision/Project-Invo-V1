#!/usr/bin/env bash
# Linux/macOS launcher. Mirrors START_TRADING_AI.bat.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TRADING_AI_ROOT="$ROOT"
cd "$ROOT"

PYEXE="$ROOT/.venv/bin/python"
if [[ ! -x "$PYEXE" ]]; then
  echo "[!] No Python environment on the SSD. Run ./install.sh first." >&2
  exit 1
fi

echo "============================================================"
echo " TRADING_AI    root=$ROOT"
echo "============================================================"
"$PYEXE" scripts/system_check.py --root "$ROOT" || {
  echo; echo "SYSTEM CHECK FAILED - not starting."; exit 1; }
echo
"$PYEXE" scripts/run_pipeline.py --root "$ROOT"
