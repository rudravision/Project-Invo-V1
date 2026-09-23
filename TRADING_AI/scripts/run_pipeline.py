#!/usr/bin/env python3
"""
End-to-end pipeline: validate -> heatmap -> rank -> backtest (steps 9-12).

Runs entirely locally against the SSD database. No internet required.

Usage:
    python scripts/run_pipeline.py --root /path/to/TRADING_AI
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app.analytics.ranking import (RankConfig, rank_stocks, render_heatmap_text,
                                   render_ranking_text, sector_heatmap,
                                   components_json)
from app.backtest.engine import BacktestConfig, CostModel, run_backtest, save_result
from app.core.config import load_settings
from app.data.quality import gate_signal, validate_daily
from app.db.database import Database, atomic_write_text, graceful_shutdown


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="TRADING_AI root")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--skip-backtest", action="store_true")
    args = ap.parse_args()

    st = load_settings(args.root)
    root = st.root
    db = Database(st.db_path)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    print("=" * 100)
    print(f"TRADING_AI PIPELINE   root={root}")
    print("=" * 100)

    conn = db.connect()
    try:
        daily = pd.read_sql_query(
            "SELECT symbol,date,open,high,low,close,volume,is_synthetic"
            " FROM daily_ohlc ORDER BY symbol,date", conn)
        index_df = pd.read_sql_query(
            "SELECT index_name,date,close,is_synthetic FROM index_ohlc"
            " ORDER BY index_name,date", conn)
        sectors = dict(conn.execute(
            "SELECT symbol,sector FROM symbols").fetchall())
        holidays = {r[0] for r in conn.execute(
            "SELECT date FROM trading_calendar WHERE is_holiday=1")}
    finally:
        conn.close()

    if daily.empty:
        print("\nNo daily data in the database.")
        print("Run one of:")
        print("  python scripts/bootstrap_data.py           # real data")
        print("  python scripts/make_demo_dataset.py --db " + str(st.db_path))
        return 1

    synthetic = bool(daily["is_synthetic"].max())
    if synthetic:
        print("\n" + "!" * 100)
        print("! DATASET IS SYNTHETIC DEMO DATA. Nothing below reflects the "
              "real market. Signals are BLOCKED.")
        print("!" * 100)

    # ---- STEP 9: validate -------------------------------------------------
    print("\n[9] DATA VALIDATION")
    print("-" * 100)
    rep = validate_daily(daily, holidays=holidays)
    print(rep.summary())
    rep.persist(db)

    allowed, gate_msg = gate_signal(rep, is_synthetic=synthetic)
    print("\nSIGNAL GATE: " + ("ALLOWED" if allowed else "BLOCKED"))
    print(gate_msg)

    # ---- STEP 10: heatmap -------------------------------------------------
    print("\n[10] NIFTY + SECTOR HEATMAP")
    print("-" * 100)
    hm = sector_heatmap(index_df)
    hm_txt = render_heatmap_text(hm, synthetic=synthetic)
    print(hm_txt)
    atomic_write_text(reports / "heatmap_latest.txt", hm_txt)
    if not hm.empty:
        hm.to_csv(reports / "heatmap_latest.csv", index=False)

    # ---- STEP 11: ranking -------------------------------------------------
    print("\n[11] STOCK RANKING PROTOTYPE")
    print("-" * 100)
    ranked = rank_stocks(daily, RankConfig(), sectors=sectors)
    rk_txt = render_ranking_text(ranked, top_n=args.top, synthetic=synthetic)
    print(rk_txt)
    atomic_write_text(reports / "ranking_latest.txt", rk_txt)
    if not ranked.empty:
        ranked.to_csv(reports / "ranking_latest.csv", index=False)
        as_of = pd.to_datetime(ranked["date"].iloc[0]).date().isoformat()
        with db.tx() as c:
            c.execute("DELETE FROM signals WHERE as_of_date=?", (as_of,))
            c.executemany(
                "INSERT INTO signals (as_of_date,symbol,rank,score,components,"
                "data_quality_ok,is_synthetic,notes) VALUES (?,?,?,?,?,?,?,?)",
                [(as_of, r["symbol"], int(r["rank"]), float(r["score"]),
                  components_json(r), int(allowed), int(synthetic),
                  "rule-based prototype v1")
                 for _, r in ranked.head(50).iterrows()])

    if not allowed:
        print("\n" + "=" * 100)
        print("NO TRADING RECOMMENDATION ISSUED.")
        print(gate_msg)
        print("=" * 100)

    # ---- STEP 12: backtest ------------------------------------------------
    if not args.skip_backtest and not ranked.empty:
        print("\n[12] BACKTEST")
        print("-" * 100)
        dates = pd.to_datetime(daily["date"])
        start = (dates.min() + pd.Timedelta(days=200)).date()
        end = dates.max().date()
        if start >= end:
            print("Not enough history to backtest (need >200 warm-up bars).")
        else:
            bt_cfg = BacktestConfig(start=start, end=end,
                                    rebalance_days=5, top_n=5)
            bench = (index_df[index_df["index_name"] == "NIFTY 50"]
                     [["date", "close"]] if "NIFTY 50" in
                     set(index_df["index_name"]) else None)
            try:
                res = run_backtest(daily, bt_cfg, RankConfig(),
                                   CostModel(), benchmark=bench)
                print(res.report())
                paths = save_result(res, root / "backtests", "rank_v1")
                print(f"\nSaved: {paths['base']}_*")
            except ValueError as e:
                print(f"Backtest skipped: {e}")

    graceful_shutdown(db)
    print("\nDone. Reports in " + str(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
