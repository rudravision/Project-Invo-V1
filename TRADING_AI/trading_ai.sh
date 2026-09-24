#!/usr/bin/env bash
# TRADING_AI launcher (Linux / macOS). Opens the desktop window.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(dirname "$ROOT")/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "TRADING_AI is not installed yet. Run ./install.sh first."
  exit 1
fi
exec "$PY" "$ROOT/scripts/launch_gui.py" --root "$ROOT" "$@"
