#!/usr/bin/env python3
"""
Pre-flight SYSTEM CHECK (spec 20).

Verifies, with clear human-readable results:
  SSD available, internet available, market-data source available,
  database healthy, Python environment available, credentials available,
  Telegram connection available, disk space sufficient.

Exit codes:  0 = all critical checks pass,  1 = a critical check failed.
Warnings alone do not fail the run.
"""

from __future__ import annotations

import argparse
import importlib
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


class Checks:
    def __init__(self):
        self.rows: list[tuple[str, str, str, bool]] = []

    def add(self, name: str, status: str, detail: str, critical: bool = True):
        self.rows.append((name, status, detail, critical))
        icon = {PASS: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}[status]
        print(f"{icon}  {name:<28} {detail}")

    @property
    def failed_critical(self) -> list[tuple]:
        return [r for r in self.rows if r[1] == FAIL and r[3]]


def check_python(c: Checks):
    v = sys.version_info
    if v < (3, 9):
        c.add("Python version", FAIL,
              f"{v.major}.{v.minor} found; 3.9+ required")
    else:
        c.add("Python version", PASS, f"{v.major}.{v.minor}.{v.micro}")

    required = ["pandas", "numpy", "requests", "yaml"]
    optional = ["matplotlib", "sklearn", "streamlit"]
    missing = [m for m in required if not _has(m)]
    if missing:
        c.add("Required packages", FAIL,
              f"Missing: {', '.join(missing)}. Run INSTALL.")
    else:
        c.add("Required packages", PASS, ", ".join(required) + " present")
    miss_opt = [m for m in optional if not _has(m)]
    c.add("Optional packages", WARN if miss_opt else PASS,
          (f"Missing (non-fatal): {', '.join(miss_opt)}"
           if miss_opt else "all present"), critical=False)


def _has(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except ImportError:
        return False


def check_ssd(c: Checks, explicit_root):
    from app.core.ssd import (SSDNotFoundError, detect_ssd, free_space_report,
                              human_report, resolve_project_root)
    try:
        root = resolve_project_root(explicit_root)
    except SSDNotFoundError as e:
        c.add("SSD detected", FAIL, "No external SSD found")
        print("\n" + str(e) + "\n")
        return None

    ssd = detect_ssd()
    if ssd:
        c.add("SSD detected", PASS,
              f"{ssd.label or 'unlabelled'} at {ssd.path} "
              f"({ssd.total_gb:.0f} GB, removable={ssd.removable})")
    else:
        c.add("SSD detected", WARN,
              f"Using configured path {root} (not auto-detected as removable)",
              critical=False)

    if not root.exists():
        c.add("Project folder", WARN, f"{root} does not exist yet (START creates it)",
              critical=False)
        return root

    sp = free_space_report(root)
    from app.core.config import load_settings
    try:
        st = load_settings(str(root), create=False)
        minfree = st.min_free_gb
    except Exception:
        minfree = 20.0
    status = PASS if sp["free_gb"] >= minfree else FAIL
    c.add("Disk space", status,
          f"{sp['free_gb']:.1f} GB free of {sp['total_gb']:.1f} GB "
          f"({sp['used_pct']}% used); minimum {minfree} GB")
    return root


def check_internet(c: Checks):
    hosts = [("1.1.1.1", 53), ("8.8.8.8", 53)]
    for h, p in hosts:
        try:
            with socket.create_connection((h, p), timeout=5):
                c.add("Internet", PASS, f"reachable via {h}:{p}")
                return True
        except OSError:
            continue
    c.add("Internet", FAIL,
          "No outbound connectivity. Offline analysis still works; "
          "downloads and alerts will not.")
    return False


def check_sources(c: Checks, root: Path, online: bool):
    if not online:
        c.add("Market data source", FAIL, "skipped - no internet")
        return
    try:
        from app.core.config import load_settings
        from app.data.providers.nse_archive import NSEArchiveProvider
        st = load_settings(str(root), create=False)
        p = NSEArchiveProvider(st.source_defaults())
        ok, detail = p.health_check()
        c.add("Market data source", PASS if ok else FAIL, f"nse_archive: {detail}")
    except Exception as e:  # noqa: BLE001
        c.add("Market data source", FAIL, f"{type(e).__name__}: {e}")

    probes = sorted((root / "reports").glob("source_probe_*.json"))
    if probes:
        try:
            rep = json.loads(probes[-1].read_text())
            w = sum(1 for r in rep["results"] if r["status"] == "WORKING")
            c.add("Last source probe", PASS if w else WARN,
                  f"{rep['generated_at_utc']}: {w} working", critical=False)
        except (OSError, ValueError):
            pass
    else:
        c.add("Last source probe", WARN,
              "never run - do: python scripts/probe_sources.py", critical=False)


def check_database(c: Checks, root: Path):
    try:
        from app.core.config import load_settings
        from app.db.database import Database
        st = load_settings(str(root), create=False)
        if not st.db_path.exists():
            c.add("Database", WARN, f"not created yet at {st.db_path}",
                  critical=False)
            return
        db = Database(st.db_path)
        ok, detail = db.integrity_check()
        size = st.db_path.stat().st_size / 1024**2
        cov = db.coverage()
        c.add("Database", PASS if ok else FAIL,
              f"{detail} | {size:.1f} MB | {cov['rows']} daily rows, "
              f"{cov['symbols']} symbols, {cov['min_date']}..{cov['max_date']}")

        bks = db.verify_backups(st.backups_dir)
        bad = [b for b in bks if b["ok"] is False]
        if bad:
            c.add("Backups", FAIL, f"{len(bad)} of {len(bks)} FAIL checksum")
        else:
            c.add("Backups", PASS if bks else WARN,
                  f"{len(bks)} verified" if bks else "no backups yet",
                  critical=False)
    except Exception as e:  # noqa: BLE001
        c.add("Database", FAIL, f"{type(e).__name__}: {e}")


def check_credentials(c: Checks, root: Path):
    from app.core.config import load_credentials
    creds = load_credentials(root)
    have = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if creds.get(k)]
    broker = [k for k in creds if k.startswith(("UPSTOX", "FYERS", "BREEZE"))]
    c.add("Telegram credentials", PASS if len(have) == 2 else WARN,
          "configured" if len(have) == 2 else
          "not set - alerts disabled (set TELEGRAM_BOT_TOKEN and "
          "TELEGRAM_CHAT_ID in config/.env)", critical=False)
    c.add("Broker credentials", PASS if broker else WARN,
          f"{len(broker)} keys present" if broker else
          "none - free public sources only (fine to start)", critical=False)
    return creds


def check_telegram(c: Checks, creds: dict, online: bool):
    tok, chat = creds.get("TELEGRAM_BOT_TOKEN"), creds.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        c.add("Telegram connection", WARN, "skipped - no credentials",
              critical=False)
        return
    if not online:
        c.add("Telegram connection", WARN, "skipped - offline", critical=False)
        return
    try:
        import requests
        r = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=10)
        if r.status_code == 200 and r.json().get("ok"):
            name = r.json()["result"].get("username", "?")
            c.add("Telegram connection", PASS, f"bot @{name} reachable",
                  critical=False)
        else:
            c.add("Telegram connection", FAIL,
                  f"HTTP {r.status_code} - token may be invalid", critical=False)
    except Exception as e:  # noqa: BLE001
        c.add("Telegram connection", FAIL, f"{type(e).__name__}: {e}",
              critical=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    a = ap.parse_args()

    print("=" * 96)
    print("TRADING_AI SYSTEM CHECK")
    print("=" * 96)

    c = Checks()
    check_python(c)
    root = check_ssd(c, a.root)
    online = check_internet(c)
    if root:
        check_sources(c, root, online)
        check_database(c, root)
        creds = check_credentials(c, root)
        check_telegram(c, creds, online)

    print("=" * 96)
    n_fail = sum(1 for r in c.rows if r[1] == FAIL)
    n_warn = sum(1 for r in c.rows if r[1] == WARN)
    crit = c.failed_critical
    print(f"RESULT: {len(c.rows)} checks | {n_fail} failed | {n_warn} warnings")
    if crit:
        print("\nCRITICAL FAILURES - the system should not start:")
        for name, _, detail, _ in crit:
            print(f"  * {name}: {detail}")
        print("\nFix the items above, then run SYSTEM CHECK again.")
        return 1
    print("\nAll critical checks passed. Safe to start.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
