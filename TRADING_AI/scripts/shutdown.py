#!/usr/bin/env python3
"""Graceful shutdown: checkpoint WAL, optimise, verify integrity (spec 24)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings
from app.db.database import Database, graceful_shutdown


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--backup", action="store_true",
                    help="also take a backup before shutting down")
    a = ap.parse_args()

    st = load_settings(a.root, create=False)
    if not st.db_path.exists():
        print("No database to close. Nothing to do.")
        return 0

    db = Database(st.db_path)
    ok, detail = db.integrity_check()
    print(f"Integrity: {'OK' if ok else 'FAILED'} - {detail}")

    if a.backup:
        p = db.backup(st.backups_dir, keep=10)
        print(f"Backup written: {p.name}")

    graceful_shutdown(db)
    print("Database checkpointed and closed cleanly. Safe to unplug the SSD.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
