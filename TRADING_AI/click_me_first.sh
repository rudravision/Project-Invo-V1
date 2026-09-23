#!/usr/bin/env bash
# TRADING_AI - START HERE (Linux / macOS version of CLICK_ME_FIRST.bat)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TRADING_AI_ROOT="$ROOT"
cd "$ROOT"

PYEXE="$ROOT/.venv/bin/python"
if [[ ! -x "$PYEXE" ]]; then
  echo "  First time here - setting up (2-5 minutes, once only)."
  command -v python3 >/dev/null || {
    echo "  Python 3 is not installed. Install it, then run this again."; exit 1; }
  python3 -m venv "$ROOT/.venv" || { echo "  Could not create environment."; exit 1; }
  "$ROOT/.venv/bin/pip" install --upgrade pip --quiet
  "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt" || {
    echo "  Download failed - check your internet."; exit 1; }
  "$PYEXE" -c "import sys;sys.path.insert(0,'$ROOT');from pathlib import Path;from app.core.ssd import ensure_project_root;ensure_project_root(Path('$ROOT'))"
  [[ -f "$ROOT/config/.env" ]] || { printf 'TELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\nUPSTOX_API_KEY=\nUPSTOX_API_SECRET=\nUPSTOX_ACCESS_TOKEN=\n' > "$ROOT/config/.env"; chmod 600 "$ROOT/config/.env"; }
  echo "  Setup complete."
fi
exec "$PYEXE" "$ROOT/scripts/assistant.py"
