"""
Desktop launcher.

Starts the local server, then opens it in the best window available:
  1. pywebview  - a real borderless desktop window (installed by INSTALL.bat)
  2. Chrome / Edge in --app mode - looks like a desktop app, no address bar
  3. your normal browser - always works

The server only listens on 127.0.0.1, so nothing is exposed to the network.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import load_settings, setup_logging   # noqa: E402
from app.gui.server import create_app                      # noqa: E402

log = logging.getLogger(__name__)
TITLE = "TRADING_AI"


def free_port(preferred: int = 8777) -> int:
    for p in [preferred] + list(range(8778, 8800)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until_up(port: int, timeout: float = 45.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.25)
    return False


def _chrome_paths():
    names = ["chrome", "google-chrome", "msedge", "chromium", "chromium-browser"]
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if Path(p).exists():
            return p
    return None


def open_window(url: str, profile_dir: Path) -> str:
    # 1. pywebview
    try:
        import webview  # noqa: F401
        return "pywebview"
    except ImportError:
        pass

    # 2. chromeless browser window
    exe = _chrome_paths()
    if exe:
        profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(
                [exe, f"--app={url}", f"--user-data-dir={profile_dir}",
                 "--window-size=1500,950", "--no-first-run",
                 "--no-default-browser-check"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "app-window"
        except OSError:
            pass

    # 3. default browser
    import webbrowser
    webbrowser.open(url)
    return "browser"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--no-window", action="store_true",
                    help="start the server only")
    a = ap.parse_args()

    settings = load_settings(a.root)
    setup_logging(settings)
    port = free_port(a.port)
    url = f"http://127.0.0.1:{port}/"

    app = create_app(a.root)

    def serve():
        app.run(host="127.0.0.1", port=port, threaded=True,
                use_reloader=False, debug=False)

    t = threading.Thread(target=serve, daemon=True, name="web")
    t.start()

    print(f"{TITLE} starting...")
    if not wait_until_up(port):
        print("The interface did not start. See the log at "
              f"{settings.logs_dir / 'trading_ai.log'}")
        return 1
    print(f"{TITLE} is running at {url}")

    if a.no_window:
        try:
            while t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return 0

    mode = open_window(url, settings.root / "config" / ".browser_profile")
    if mode == "pywebview":
        import webview
        webview.create_window(TITLE, url, width=1500, height=950,
                              min_size=(1100, 700))
        webview.start()
        return 0

    print("Close this window to shut TRADING_AI down.")
    try:
        while t.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
