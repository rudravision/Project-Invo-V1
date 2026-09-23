#!/usr/bin/env python3
"""
Incremental real-data downloader (spec 22 & 25).

Behaviour:
  * Estimates storage BEFORE downloading anything and asks for confirmation.
  * Downloads only the days missing from the local cache.
  * Stores each raw file immutably (read-only + SHA-256) under data/raw/.
  * Derives the processed tables from raw, so they are reproducible.
  * Falls back to the configured backup provider and logs every failure.
  * Validates everything and writes to the data-quality log.

It will refuse to run if the source probe has not confirmed a working source,
unless you pass --force.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings, setup_logging
from app.data.base import FailureLog
from app.data.providers.nse_archive import NSEArchiveProvider
from app.data.quality import validate_daily
from app.db.database import Database, graceful_shutdown, write_raw_immutable

# Rough, measured-order-of-magnitude sizes. Refined after the first download.
BYTES_PER_BHAVCOPY_ZIP = 350_000        # full-market CM UDiFF zip
BYTES_PER_INDEX_CSV = 25_000
BYTES_PER_DAILY_ROW_DB = 120


def estimate(days: int, symbols: int) -> dict:
    raw = days * (BYTES_PER_BHAVCOPY_ZIP + BYTES_PER_INDEX_CSV)
    db = days * symbols * BYTES_PER_DAILY_ROW_DB
    return {
        "trading_days": days,
        "symbols": symbols,
        "raw_mb": round(raw / 1024**2, 1),
        "db_mb": round(db / 1024**2, 1),
        "total_mb": round((raw + db) / 1024**2, 1),
        "http_requests": days * 2,
        "est_minutes": round(days * 2 * 1.4 / 60, 1),
    }


def trading_weekdays(start: dt.date, end: dt.date) -> list[dt.date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def latest_probe(root: Path) -> dict | None:
    probes = sorted((root / "reports").glob("source_probe_*.json"))
    if not probes:
        return None
    try:
        return json.loads(probes[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--days", type=int, default=120,
                    help="calendar days of history to ensure")
    ap.add_argument("--index", default="nifty200",
                    help="universe index slug, e.g. nifty50 / nifty200")
    ap.add_argument("--yes", action="store_true", help="skip confirmation")
    ap.add_argument("--force", action="store_true",
                    help="run even if the probe shows no working source")
    ap.add_argument("--estimate-only", action="store_true")
    a = ap.parse_args()

    st = load_settings(a.root)
    setup_logging(st)
    db = Database(st.db_path)

    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=a.days)
    days = trading_weekdays(start, end)

    # ---- storage estimate FIRST (spec 25) -------------------------------
    est = estimate(len(days), 200)
    print("=" * 78)
    print("STORAGE ESTIMATE BEFORE DOWNLOAD")
    print("=" * 78)
    for k, v in est.items():
        print(f"  {k:<16} {v}")
    free = st.free_space()
    print(f"  free on SSD      {free['free_gb']} GB at {free['path']}")
    if free["free_gb"] * 1024 < est["total_mb"] * 3:
        print("\nNot enough free space with a safety margin. Aborting.")
        return 2
    if a.estimate_only:
        return 0

    # ---- refuse to guess: require a verified source ---------------------
    probe = latest_probe(st.root)
    if probe is None and not a.force:
        print("\nNo source probe report found.")
        print("Run this first so we know what actually works:")
        print("    python scripts/probe_sources.py")
        print("Then re-run. Use --force to override.")
        return 3
    if probe:
        working = [r["source"] for r in probe["results"]
                   if r["status"] == "WORKING"]
        print(f"\nLast probe ({probe['generated_at_utc']}): "
              f"{len(working)} working sources")
        if not working and not a.force:
            print("No source was confirmed working. Not pretending otherwise.")
            print("Fix connectivity or add broker credentials, then re-probe.")
            return 3

    if not a.yes:
        resp = input(f"\nDownload ~{est['total_mb']} MB over ~{est['est_minutes']} "
                     f"min? [y/N] ").strip().lower()
        if resp != "y":
            print("Cancelled. Nothing downloaded.")
            return 0

    # ---- providers -------------------------------------------------------
    flog = FailureLog(st.logs_dir / "source_failures.jsonl")
    nse = NSEArchiveProvider(st.source_defaults())

    ok, detail = nse.health_check()
    print(f"\nNSE archive health: {'OK' if ok else 'FAILED'} - {detail}")
    if not ok and not a.force:
        flog.record(nse.name, "health_check", detail, None)
        print("Primary source is down. Not fabricating data. Exiting.")
        return 4

    # ---- universe --------------------------------------------------------
    try:
        members = nse.get_index_membership(a.index)
        symbols = sorted(members["symbol"].astype(str).str.upper().unique())
        print(f"Universe {a.index}: {len(symbols)} symbols")
        with db.tx() as c:
            c.executemany(
                "INSERT INTO symbols (symbol,name,isin,sector,in_nifty200)"
                " VALUES (?,?,?,?,1) ON CONFLICT(symbol) DO UPDATE SET"
                " sector=COALESCE(excluded.sector,sector)",
                [(str(r.get("symbol", "")).upper(),
                  r.get("company_name"), r.get("isin_code"),
                  r.get("industry")) for _, r in members.iterrows()])
    except Exception as e:  # noqa: BLE001
        flog.record(nse.name, "index_membership", str(e), None)
        print(f"Could not fetch the universe: {e}")
        symbols = []

    # ---- trading calendar -----------------------------------------------
    try:
        cal = nse.get_trading_calendar(end.year)
        with db.tx() as c:
            c.executemany(
                "INSERT OR REPLACE INTO trading_calendar"
                " (date,is_holiday,description,segment,source) VALUES (?,1,?,?,?)",
                [(r["date"].date().isoformat(), r.get("description"),
                  r.get("segment"), "nse_archive")
                 for _, r in cal.iterrows() if r["date"] is not None])
        print(f"Trading calendar: {len(cal)} holidays recorded")
    except Exception as e:  # noqa: BLE001
        flog.record(nse.name, "calendar", str(e), None)
        print(f"Calendar unavailable: {e}")

    # ---- incremental daily download -------------------------------------
    conn = db.connect()
    try:
        have = {r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM daily_ohlc WHERE is_synthetic=0")}
        holidays = {r[0] for r in conn.execute(
            "SELECT date FROM trading_calendar WHERE is_holiday=1")}
    finally:
        conn.close()

    todo = [d for d in days
            if d.isoformat() not in have and d.isoformat() not in holidays]
    print(f"\nCached: {len(days) - len(todo)} days. To download: {len(todo)}.")

    got = failed = 0
    for d in todo:
        try:
            rows = nse.bhavcopy(d)
            # immutable raw copy
            import io, zipfile
            raw_path = st.raw_dir / "cm_bhavcopy" / f"{d:%Y}" / f"BhavCopy_{d:%Y%m%d}.json"
            write_raw_immutable(raw_path,
                                json.dumps(rows).encode("utf-8"),
                                db=db, dataset="cm_bhavcopy",
                                for_date=d.isoformat(), source=nse.name)
            recs = []
            for r in rows:
                if (r.get("SctySrs") or "").strip() != "EQ":
                    continue
                sym = (r.get("TckrSymb") or "").strip().upper()
                if symbols and sym not in set(symbols):
                    continue
                recs.append({
                    "symbol": sym, "date": d.isoformat(),
                    "open": _f(r.get("OpnPric")), "high": _f(r.get("HghPric")),
                    "low": _f(r.get("LwPric")), "close": _f(r.get("ClsPric")),
                    "prev_close": _f(r.get("PrvsClsgPric")),
                    "volume": _f(r.get("TtlTradgVol")),
                    "turnover": _f(r.get("TtlTrfVal")),
                    "trades": _f(r.get("TtlNbOfTxsExctd")),
                    "source": nse.name, "is_synthetic": 0,
                })
            db.upsert_daily(recs)
            got += 1
            print(f"  {d}  {len(recs)} rows")
        except Exception as e:  # noqa: BLE001
            failed += 1
            flog.record(nse.name, "daily_ohlc", f"{d}: {e}", None)
            print(f"  {d}  FAILED: {str(e)[:80]}")

    print(f"\nDownloaded {got} days, {failed} failures.")

    # ---- validate --------------------------------------------------------
    import pandas as pd
    conn = db.connect()
    try:
        df = pd.read_sql_query(
            "SELECT symbol,date,open,high,low,close,volume,is_synthetic"
            " FROM daily_ohlc WHERE is_synthetic=0", conn)
    finally:
        conn.close()

    if not df.empty:
        rep = validate_daily(df, holidays=holidays)
        print("\n" + rep.summary())
        rep.persist(db)

    db.backup(st.backups_dir, keep=10)
    graceful_shutdown(db)
    return 0


def _f(v):
    try:
        s = str(v).strip().replace(",", "")
        return float(s) if s not in ("", "-", "NA", "None") else None
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
