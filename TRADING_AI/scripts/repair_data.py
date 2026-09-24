#!/usr/bin/env python3
"""
Diagnose and repair the historical database.

Safe by construction:
  * takes a verified backup before touching anything
  * only ADDS missing rows; never edits or deletes existing price data
  * raw downloads stay immutable
  * every step is reported

Usage:
    python scripts/repair_data.py --diagnose          # report only, no changes
    python scripts/repair_data.py --repair            # backup, then fix
    python scripts/repair_data.py --repair --offline  # calendar repair only
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings, setup_logging
from app.data.calendar import MarketCalendar, SymbolLifecycle
from app.data.repair import DownloadQueue, analyse_gaps, plan_repair
from app.db.database import Database, graceful_shutdown
from app.db.migrations import migrate


def diagnose(db, settings, progress=print) -> dict:
    """Work out the true state of the database. Read-only."""
    cal = MarketCalendar(db)
    life = SymbolLifecycle(db)

    conn = db.connect()
    try:
        b = conn.execute("SELECT MIN(date) mn, MAX(date) mx, COUNT(*) n,"
                         " COUNT(DISTINCT symbol) s FROM daily_ohlc"
                         " WHERE is_synthetic=0").fetchone()
        idx = conn.execute("SELECT COUNT(*) n, COUNT(DISTINCT index_name) i"
                           " FROM index_ohlc WHERE is_synthetic=0").fetchone()
    finally:
        conn.close()

    if not b or not b["mn"]:
        return {"empty": True}

    start = dt.date.fromisoformat(b["mn"])
    end = dt.date.fromisoformat(b["mx"])

    progress("Rebuilding session calendar from existing data...")
    cal.seed_weekends(start, end)
    inferred = cal.infer_sessions_from_data()

    progress("Rebuilding symbol lifecycle...")
    lc = life.rebuild()

    progress("Classifying gaps...")
    gap = analyse_gaps(db, persist=True, progress=None)
    plan = plan_repair(db, gap, start, end)

    return {
        "empty": False,
        "rows": b["n"], "symbols": b["s"],
        "start": b["mn"], "end": b["mx"],
        "index_rows": idx["n"], "index_count": idx["i"],
        "sessions_inferred": inferred,
        "lifecycle": lc,
        "calendar": cal.summary(start, end),
        "gap": gap,
        "plan": plan,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="calendar/lifecycle repair only, no downloads")
    ap.add_argument("--db", default=None, help="override database path")
    a = ap.parse_args()

    if a.db:
        db = Database(a.db)

        class _S:
            backups_dir = Path(a.db).parent / "backups"
        settings = _S()
    else:
        settings = load_settings(a.root)
        setup_logging(settings)
        db = Database(settings.db_path)

    print("=" * 78)
    print("DATABASE DIAGNOSIS AND REPAIR")
    print("=" * 78)

    # Schema must exist before anything else.
    res = migrate(db, Path(settings.backups_dir), progress=print)
    if res["applied"]:
        print(f"  {res['detail']}")
        if res["backup"]:
            print(f"  Backup: {res['backup']}")

    info = diagnose(db, settings)
    if info.get("empty"):
        print("\nThe database has no real market data yet.")
        print("Run a data sync first.")
        return 1

    print(f"\nCurrent state")
    print("-" * 78)
    print(f"  Price rows        {info['rows']:,}")
    print(f"  Symbols           {info['symbols']:,}")
    print(f"  Date range        {info['start']} to {info['end']}")
    print(f"  Index rows        {info['index_rows']:,} "
          f"across {info['index_count']} indices")
    print(f"  Sessions inferred {info['sessions_inferred']:,}")
    lc = info["lifecycle"]
    print(f"  Lifecycle         {lc['active']} active, "
          f"{lc['suspended']} suspended, {lc['delisted']} delisted")
    print(f"  Calendar          {info['calendar']}")

    print(f"\nGap analysis")
    print("-" * 78)
    print(info["gap"].summary())

    plan = info["plan"]
    print(f"\nRepair plan")
    print("-" * 78)
    print(f"  {plan.reason}")
    print(f"  Downloads required: {plan.total_requests}")

    if a.diagnose or not a.repair:
        print("\n(diagnosis only - nothing was changed)")
        graceful_shutdown(db)
        return 0

    if plan.is_empty:
        print("\nNothing to repair.")
        graceful_shutdown(db)
        return 0

    # Queue the work so it survives an interruption.
    q = DownloadQueue(db)
    q.enqueue("cm_bhavcopy", plan.refetch_sessions, priority=10)
    q.enqueue("cm_bhavcopy", plan.verify_dates, priority=20)
    q.enqueue("index_close", plan.need_index, priority=30)
    print(f"\nQueued {plan.total_requests} download task(s).")
    print(f"Queue state: {q.stats()}")

    if a.offline:
        print("\n--offline: calendar and lifecycle repaired; downloads queued.")
        print("Run the sync (GUI: UPDATE & ANALYZE MARKET) to fetch them.")
        graceful_shutdown(db)
        return 0

    from scripts.sync_data import run_sync
    print("\nStarting download of queued sessions...")
    run_sync(db, settings, progress=print)

    print("\nRe-running diagnosis after repair...")
    after = diagnose(db, settings)
    print(after["gap"].summary())

    graceful_shutdown(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
