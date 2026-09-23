#!/usr/bin/env bash
# Creates the Python environment ON THE SSD.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

command -v python3 >/dev/null || { echo "[!] python3 not found"; exit 1; }
echo "Found $(python3 --version)"

[[ -x "$ROOT/.venv/bin/python" ]] || python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install --upgrade pip
"$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"

"$ROOT/.venv/bin/python" - <<PY
import sys; sys.path.insert(0, "$ROOT")
from pathlib import Path
from app.core.ssd import ensure_project_root
ensure_project_root(Path("$ROOT")); print("  folders ready")
PY

if [[ ! -f "$ROOT/config/.env" ]]; then
cat > "$ROOT/config/.env" <<'ENV'
# TRADING_AI credentials. KEEP PRIVATE. Never commit.
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
UPSTOX_API_KEY=
UPSTOX_API_SECRET=
UPSTOX_ACCESS_TOKEN=
ENV
chmod 600 "$ROOT/config/.env"
fi

echo
echo "INSTALL COMPLETE. Next: ./system_check.sh"
