#!/usr/bin/env python3
"""
Resumable, incremental market-data sync.

This replaces the fragile loop in bootstrap_data.py that silently skipped any
day whose download failed and never returned for it -- the direct cause of
the 7,600 "missing candles".

What is different:
  * every target session goes into a persistent queue, so an interrupted run
    resumes exactly where it stopped
  * a failed day is RETRIED (up to max_attempts), not abandoned
  * a 404 on a weekday is positive evidence the market was CLOSED, so the
    date is recorded as a HOLIDAY rather than silently dropped
  * index and sector data are downloaded alongside prices (the old code never
    fetched indices at all, hence "No index data available")
  * nothing is ever deleted; only missing rows are added
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings, setup_logging
from app.data.base import FailureLog, NotAvailableError
from app.data.calendar import (HOLIDAY, SESSION, MarketCalendar,
                               SymbolLifecycle)
from app.data.providers.nse_archive import NSEArchiveProvider
from app.data.repair import DownloadQueue
from app.db.database import Database, graceful_shutdown, write_raw_immutable
from app.db.migrations import migrate

PERIODS = {
    "3m": 92, "6m": 183, "1y": 366, "2y": 731, "3y": 1096,
    "5y": 1827, "max": 3653,
}

# Indices we keep history for.
CORE_INDICES = [
    "NIFTY 50", "NIFTY 100", "NIFTY 200", "NIFTY 500",
    "NIFTY BANK", "NIFTY IT", "NIFTY AUTO", "NIFTY FMCG", "NIFTY PHARMA",
    "NIFTY METAL", "NIFTY REALTY", "NIFTY ENERGY",
    "NIFTY FINANCIAL SERVICES", "NIFTY PSU BANK", "NIFTY PVT BANK",
    "NIFTY MEDIA", "NIFTY HEALTHCARE INDEX", "NIFTY CONSUMER DURABLES",
    "NIFTY OIL & GAS", "NIFTY INFRASTRUCTURE", "NIFTY COMMODITIES",
    "NIFTY MIDCAP 100", "NIFTY SMALLCAP 100", "INDIA VIX",
]

# Membership files we pull for sector mapping.
MEMBERSHIP_SLUGS = [
    "nifty50", "nifty100", "nifty200", "nifty500",
    "niftybank", "niftyit", "niftyauto", "niftyfmcg", "niftypharma",
    "niftymetal", "niftyrealty", "niftyenergy", "niftyfinancialservices",
    "niftypsubank", "niftyprivatebank", "niftymedia", "niftyhealthcare",
    "niftyconsumerdurables", "niftyoilgas", "niftyinfra",
]

SECTOR_FROM_SLUG = {
    "niftybank": "Banking", "niftyit": "Information Technology",
    "niftyauto": "Automobile", "niftyfmcg": "FMCG",
    "niftypharma": "Pharmaceuticals", "niftymetal": "Metals & Mining",
    "niftyrealty": "Realty", "niftyenergy": "Energy",
    "niftyfinancialservices": "Financial Services",
    "niftypsubank": "PSU Banks", "niftyprivatebank": "Private Banks",
    "niftymedia": "Media", "niftyhealthcare": "Healthcare",
    "niftyconsumerdurables": "Consumer Durables",
    "niftyoilgas": "Oil & Gas", "niftyinfra": "Infrastructure",
}


def _f(v):
    try:
        s = str(v).strip().replace(",", "")
        return float(s) if s not in ("", "-", "NA", "None", "nan") else None
    except (TypeError, ValueError):
        return None


def weekdays(start: dt.date, end: dt.date) -> list[dt.date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


# --------------------------------------------------------------------------- #
def run_sync(db, settings, *, period: str = "2y", universe: str = "nifty200",
             progress=None, should_stop=None, max_attempts: int = 3,
             fetch_delivery: bool = True) -> dict:
    """Bring the database up to date. Safe to interrupt and re-run.

    `progress(message, current, total)` is called throughout so a GUI can
    show a live progress bar without freezing.
    """
    def say(msg, cur=None, tot=None):
        if progress:
            progress(msg, cur, tot)

    def stop() -> bool:
        return bool(should_stop and should_stop())

    stats = {"sessions_downloaded": 0, "rows_added": 0, "holidays_found": 0,
             "index_days": 0, "failures": 0, "skipped_existing": 0,
             "delivery_days": 0, "stopped_early": False}

    migrate(db, Path(settings.backups_dir), progress=lambda m: say(m))

    cal = MarketCalendar(db)
    life = SymbolLifecycle(db)
    q = DownloadQueue(db)
    flog = FailureLog(Path(settings.logs_dir) / "source_failures.jsonl")
    nse = NSEArchiveProvider(settings.source_defaults())

    end = dt.date.today()
    start = end - dt.timedelta(days=PERIODS.get(period, 731))

    # ---- 1. calendar foundation -----------------------------------------
    say("Checking market calendar...")
    cal.seed_weekends(start, end)
    cal.infer_sessions_from_data()

    try:
        for yr in range(start.year, end.year + 1):
            c = nse.get_trading_calendar(yr)
            if c is not None and len(c):
                n = cal.load_holidays(
                    [r for r in c["date"].dropna().tolist()], source="nse")
                stats["holidays_found"] += n
        say(f"Loaded {stats['holidays_found']} holidays from NSE")
    except Exception as e:  # noqa: BLE001
        flog.record(nse.name, "calendar", str(e), "fixed-holiday fallback")
        n = cal.fallback_fixed_holidays(start, end)
        say(f"Holiday list unavailable; applied {n} fixed national holidays")

    # ---- 2. universe + sector mapping -----------------------------------
    say("Updating index membership and sector mapping...")
    members: dict[str, dict] = {}
    for slug in MEMBERSHIP_SLUGS:
        if stop():
            break
        try:
            m = nse.get_index_membership(slug)
        except Exception as e:  # noqa: BLE001
            flog.record(nse.name, f"membership:{slug}", str(e), None)
            continue
        symcol = next((c for c in ("symbol", "Symbol") if c in m.columns), None)
        if symcol is None:
            continue
        rows = []
        for _, r in m.iterrows():
            sym = str(r.get(symcol, "")).strip().upper()
            if not sym:
                continue
            sector = SECTOR_FROM_SLUG.get(slug) or r.get("industry")
            rows.append((slug, sym, sector, "nse_archive"))
            info = members.setdefault(sym, {})
            if slug in SECTOR_FROM_SLUG:
                info["sector"] = SECTOR_FROM_SLUG[slug]
            elif r.get("industry") and "industry" not in info:
                info["industry"] = r.get("industry")
            info.setdefault("name", r.get("company_name"))
            info.setdefault("isin", r.get("isin_code"))
            info[f"in_{slug}"] = 1
        if rows:
            with db.tx() as c:
                c.executemany(
                    "INSERT INTO index_membership (index_slug,symbol,sector,source)"
                    " VALUES (?,?,?,?) ON CONFLICT(index_slug,symbol)"
                    " DO UPDATE SET sector=COALESCE(excluded.sector,sector)",
                    rows)

    if members:
        with db.tx() as c:
            c.executemany(
                "INSERT INTO symbols (symbol,name,isin,sector,industry,"
                " in_nifty50,in_nifty200) VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT(symbol) DO UPDATE SET"
                "  sector=COALESCE(excluded.sector, symbols.sector),"
                "  industry=COALESCE(excluded.industry, symbols.industry),"
                "  name=COALESCE(excluded.name, symbols.name),"
                "  in_nifty50=MAX(symbols.in_nifty50, excluded.in_nifty50),"
                "  in_nifty200=MAX(symbols.in_nifty200, excluded.in_nifty200)",
                [(s, i.get("name"), i.get("isin"),
                  i.get("sector") or i.get("industry"), i.get("industry"),
                  i.get("in_nifty50", 0), i.get("in_nifty200", 0))
                 for s, i in members.items()])
        say(f"Sector mapping updated for {len(members)} symbols")

    universe_syms = {s for s, i in members.items()
                     if i.get(f"in_{universe}")} or set(members)

    # ---- 3. queue every weekday that is not already resolved ------------
    conn = db.connect()
    try:
        have_days = {r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM daily_ohlc WHERE is_synthetic=0")}
        known_closed = {r[0] for r in conn.execute(
            "SELECT date FROM market_sessions WHERE status IN ('HOLIDAY','WEEKEND')")}
        have_index = {r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM index_ohlc WHERE is_synthetic=0")}
    finally:
        conn.close()

    targets = [d.isoformat() for d in weekdays(start, end)]
    todo_price = [d for d in targets if d not in have_days and d not in known_closed]
    todo_index = [d for d in targets if d not in have_index and d not in known_closed]
    stats["skipped_existing"] = len(targets) - len(todo_price)

    q.enqueue("cm_bhavcopy", todo_price, priority=10)
    q.enqueue("index_close", todo_index, priority=20)

    # A date in todo_* means the market was open (or we do not yet know) and
    # we hold NO data for it. That fact outranks a stale 'DONE' marker left
    # over from an earlier run whose rows have since been deleted or lost -
    # otherwise the queue would refuse to ever repair the hole.
    stats["requeued"] = (q.requeue("cm_bhavcopy", todo_price)
                         + q.requeue("index_close", todo_index))
    if stats["requeued"]:
        say(f"{stats['requeued']} previously downloaded day(s) are missing "
            f"from the database and will be fetched again.")

    pending_price = q.pending("cm_bhavcopy", max_attempts=max_attempts)
    pending_index = q.pending("index_close", max_attempts=max_attempts)
    total = len(pending_price) + len(pending_index)
    say(f"{stats['skipped_existing']} day(s) already stored. "
        f"{total} download task(s) queued.", 0, total)

    # ---- 4. prices -------------------------------------------------------
    done = 0
    for iso in pending_price:
        if stop():
            stats["stopped_early"] = True
            break
        d = dt.date.fromisoformat(iso)
        done += 1
        say(f"Downloading NSE data for {iso}...", done, total)
        try:
            rows = nse.bhavcopy(d)
        except NotAvailableError:
            # A weekday with no bhavcopy is positive evidence of a closure.
            cal.mark(d, HOLIDAY, evidence="no bhavcopy published",
                     source="inferred_404")
            q.mark("cm_bhavcopy", iso, "SKIPPED", "not published (closed)")
            stats["holidays_found"] += 1
            continue
        except Exception as e:  # noqa: BLE001
            q.mark("cm_bhavcopy", iso, "FAILED", str(e))
            flog.record(nse.name, "daily_ohlc", f"{iso}: {e}", None)
            stats["failures"] += 1
            continue

        try:
            raw = Path(settings.raw_dir) / "cm_bhavcopy" / f"{d:%Y}" / \
                f"BhavCopy_{d:%Y%m%d}.json"
            write_raw_immutable(raw, json.dumps(rows).encode("utf-8"),
                                db=db, dataset="cm_bhavcopy",
                                for_date=iso, source=nse.name)
        except Exception:  # noqa: BLE001
            pass

        recs, seen = [], 0
        for r in rows:
            if (r.get("SctySrs") or "").strip() != "EQ":
                continue
            sym = (r.get("TckrSymb") or "").strip().upper()
            seen += 1
            if universe_syms and sym not in universe_syms:
                continue
            recs.append({
                "symbol": sym, "date": iso,
                "open": _f(r.get("OpnPric")), "high": _f(r.get("HghPric")),
                "low": _f(r.get("LwPric")), "close": _f(r.get("ClsPric")),
                "prev_close": _f(r.get("PrvsClsgPric")),
                "volume": _f(r.get("TtlTradgVol")),
                "turnover": _f(r.get("TtlTrfVal")),
                "trades": _f(r.get("TtlNbOfTxsExctd")),
                "source": nse.name, "is_synthetic": 0,
            })
        db.upsert_daily(recs)
        cal.mark(d, SESSION, bhavcopy=True, symbol_count=seen,
                 evidence=f"bhavcopy with {seen} EQ rows", source=nse.name)
        q.mark("cm_bhavcopy", iso, "DONE")
        stats["sessions_downloaded"] += 1
        stats["rows_added"] += len(recs)

    # ---- 5. indices ------------------------------------------------------
    for iso in pending_index:
        if stop():
            stats["stopped_early"] = True
            break
        d = dt.date.fromisoformat(iso)
        done += 1
        say(f"Updating sector indices for {iso}...", done, total)
        if cal.status(d) in ("HOLIDAY", "WEEKEND"):
            q.mark("index_close", iso, "SKIPPED", "market closed")
            continue
        try:
            idf = nse.get_index_ohlc([], d, d)
        except NotAvailableError:
            q.mark("index_close", iso, "SKIPPED", "not published")
            continue
        except Exception as e:  # noqa: BLE001
            q.mark("index_close", iso, "FAILED", str(e))
            flog.record(nse.name, "index_ohlc", f"{iso}: {e}", None)
            stats["failures"] += 1
            continue

        rows = []
        for _, r in idf.iterrows():
            nm = str(r.get("symbol", "")).strip()
            if not nm:
                continue
            rows.append({
                "index_name": nm, "date": iso,
                "open": r.get("open"), "high": r.get("high"),
                "low": r.get("low"), "close": r.get("close"),
                "change_pct": r.get("change_pct"), "volume": r.get("volume"),
                "pe": r.get("pe"), "pb": r.get("pb"),
                "div_yield": r.get("div_yield"),
                "source": nse.name, "is_synthetic": 0,
            })
        db.upsert_index(rows)
        cal.mark(d, SESSION, index=True, evidence="index close file",
                 source=nse.name)
        q.mark("index_close", iso, "DONE")
        stats["index_days"] += 1

    # ---- 6. delivery (best effort, recent only) -------------------------
    if fetch_delivery and not stop():
        recent = cal.sessions_between(end - dt.timedelta(days=45), end)
        for d in recent[-20:]:
            if stop():
                break
            conn = db.connect()
            try:
                exists = conn.execute(
                    "SELECT 1 FROM delivery WHERE date=? LIMIT 1",
                    (d.isoformat(),)).fetchone()
            finally:
                conn.close()
            if exists:
                continue
            say(f"Updating delivery data for {d}...")
            try:
                dv = nse.get_delivery(d)
                with db.tx() as c:
                    c.executemany(
                        "INSERT INTO delivery (symbol,date,deliverable_qty,"
                        "delivery_pct,traded_qty,source,is_synthetic)"
                        " VALUES (?,?,?,?,?,?,0)"
                        " ON CONFLICT(symbol,date) DO UPDATE SET"
                        " delivery_pct=excluded.delivery_pct",
                        [(r["symbol"], d.isoformat(), r["deliverable_qty"],
                          r["delivery_pct"], r["traded_qty"], nse.name)
                         for _, r in dv.iterrows()])
                stats["delivery_days"] += 1
            except Exception as e:  # noqa: BLE001
                flog.record(nse.name, "delivery", f"{d}: {e}", None)

    # ---- 7. rebuild derived state ---------------------------------------
    say("Rebuilding symbol lifecycle...")
    stats["lifecycle"] = life.rebuild()
    say("Sync complete.", total, total)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--period", default="2y", choices=list(PERIODS))
    ap.add_argument("--universe", default="nifty200")
    ap.add_argument("--no-delivery", action="store_true")
    a = ap.parse_args()

    st = load_settings(a.root)
    setup_logging(st)
    db = Database(st.db_path)

    print("=" * 78)
    print(f"MARKET DATA SYNC  -  period={a.period}  universe={a.universe}")
    print("=" * 78)

    def prog(msg, cur=None, tot=None):
        if cur is not None and tot:
            print(f"  [{cur}/{tot}] {msg}")
        else:
            print(f"  {msg}")

    stats = run_sync(db, st, period=a.period, universe=a.universe,
                     progress=prog, fetch_delivery=not a.no_delivery)
    print("\nResult")
    print("-" * 78)
    for k, v in stats.items():
        print(f"  {k:<22} {v}")
    graceful_shutdown(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
