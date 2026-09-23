#!/usr/bin/env python3
"""
Generate a SYNTHETIC demo dataset so the pipeline can be tested offline.

=============================================================================
THIS IS NOT MARKET DATA. IT IS RANDOM NUMBERS.
Every row is written with is_synthetic=1. The quality gate in
app/data/quality.py refuses to emit trading signals from synthetic rows, and
the ranker/backtester stamp their output as SYNTHETIC.
Its ONLY purpose is to prove the plumbing works before real data arrives.
Replace it by running: python scripts/bootstrap_data.py --real
=============================================================================
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from app.db.database import Database

# A small, representative slice: liquid large caps across sectors.
UNIVERSE = [
    ("RELIANCE",   "Oil Gas & Consumable Fuels"),
    ("TCS",        "Information Technology"),
    ("INFY",       "Information Technology"),
    ("HDFCBANK",   "Financial Services"),
    ("ICICIBANK",  "Financial Services"),
    ("SBIN",       "Financial Services"),
    ("ITC",        "Fast Moving Consumer Goods"),
    ("HINDUNILVR", "Fast Moving Consumer Goods"),
    ("LT",         "Construction"),
    ("MARUTI",     "Automobile and Auto Components"),
    ("TATAMOTORS", "Automobile and Auto Components"),
    ("SUNPHARMA",  "Healthcare"),
    ("CIPLA",      "Healthcare"),
    ("TATASTEEL",  "Metals & Mining"),
    ("JSWSTEEL",   "Metals & Mining"),
    ("NTPC",       "Power"),
    ("POWERGRID",  "Power"),
    ("BHARTIARTL", "Telecommunication"),
    ("ASIANPAINT", "Consumer Durables"),
    ("TITAN",      "Consumer Durables"),
]

SECTOR_INDEX = {
    "Information Technology": "NIFTY IT",
    "Financial Services": "NIFTY BANK",
    "Fast Moving Consumer Goods": "NIFTY FMCG",
    "Automobile and Auto Components": "NIFTY AUTO",
    "Healthcare": "NIFTY PHARMA",
    "Metals & Mining": "NIFTY METAL",
    "Power": "NIFTY ENERGY",
    "Oil Gas & Consumable Fuels": "NIFTY ENERGY",
    "Construction": "NIFTY INFRASTRUCTURE",
    "Telecommunication": "NIFTY MEDIA",
    "Consumer Durables": "NIFTY CONSUMER DURABLES",
}


def trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def gbm_series(n: int, s0: float, mu: float, sigma: float,
               rng: np.random.Generator) -> np.ndarray:
    """Geometric Brownian Motion closes. Purely synthetic."""
    shocks = rng.normal(mu / 252, sigma / np.sqrt(252), n)
    return s0 * np.exp(np.cumsum(shocks))


def build(db: Database, days: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    end = dt.date.today() - dt.timedelta(days=1)
    while end.weekday() >= 5:
        end -= dt.timedelta(days=1)
    start = end - dt.timedelta(days=int(days * 1.45))
    dates = trading_days(start, end)
    n = len(dates)

    # A common market factor so sector/stock correlation is realistic-ish.
    market = rng.normal(0.08 / 252, 0.14 / np.sqrt(252), n)

    sector_factor = {}
    for sec in {s for _, s in UNIVERSE}:
        beta = rng.uniform(0.7, 1.3)
        idio = rng.normal(rng.uniform(-0.05, 0.12) / 252,
                          rng.uniform(0.10, 0.22) / np.sqrt(252), n)
        sector_factor[sec] = beta * market + idio

    stock_rows, sym_rows = [], []
    for sym, sec in UNIVERSE:
        beta = rng.uniform(0.6, 1.4)
        idio = rng.normal(0, rng.uniform(0.12, 0.30) / np.sqrt(252), n)
        rets = beta * sector_factor[sec] + idio
        s0 = float(rng.uniform(150, 3800))
        close = s0 * np.exp(np.cumsum(rets))

        intraday = np.abs(rng.normal(0.008, 0.004, n)) + 0.002
        openp = close * (1 + rng.normal(0, 0.004, n))
        high = np.maximum(openp, close) * (1 + intraday)
        low = np.minimum(openp, close) * (1 - intraday)
        base_vol = rng.uniform(4e5, 9e6)
        vol = base_vol * np.exp(rng.normal(0, 0.45, n))

        prev = np.concatenate([[close[0] * (1 + rng.normal(0, 0.005))],
                               close[:-1]])
        for i, d in enumerate(dates):
            stock_rows.append({
                "symbol": sym, "date": d.isoformat(),
                "open": round(float(openp[i]), 2),
                "high": round(float(high[i]), 2),
                "low": round(float(low[i]), 2),
                "close": round(float(close[i]), 2),
                "prev_close": round(float(prev[i]), 2),
                "volume": float(int(vol[i])),
                "turnover": round(float(vol[i] * close[i]), 2),
                "trades": float(int(vol[i] / rng.uniform(80, 400))),
                "source": "SYNTHETIC_DEMO",
                "is_synthetic": 1,
            })
        sym_rows.append((sym, sec))

    # Sector indices + NIFTY 50, built from the same factors.
    index_rows = []
    for sec, idx_name in SECTOR_INDEX.items():
        if idx_name in {r["index_name"] for r in index_rows}:
            continue
        f = sector_factor.get(sec)
        if f is None:
            continue
        lvl = 20000 * np.exp(np.cumsum(f))
        for i, d in enumerate(dates):
            index_rows.append({
                "index_name": idx_name, "date": d.isoformat(),
                "open": round(float(lvl[i] * (1 + rng.normal(0, 0.002))), 2),
                "high": round(float(lvl[i] * 1.004), 2),
                "low": round(float(lvl[i] * 0.996), 2),
                "close": round(float(lvl[i]), 2),
                "change_pct": round(float(f[i] * 100), 3),
                "volume": float(int(rng.uniform(1e7, 9e7))),
                "pe": round(float(rng.uniform(15, 35)), 2),
                "pb": round(float(rng.uniform(2, 6)), 2),
                "div_yield": round(float(rng.uniform(0.4, 2.0)), 2),
                "source": "SYNTHETIC_DEMO", "is_synthetic": 1,
            })

    nifty = 22000 * np.exp(np.cumsum(market))
    for i, d in enumerate(dates):
        index_rows.append({
            "index_name": "NIFTY 50", "date": d.isoformat(),
            "open": round(float(nifty[i] * (1 + rng.normal(0, 0.002))), 2),
            "high": round(float(nifty[i] * 1.003), 2),
            "low": round(float(nifty[i] * 0.997), 2),
            "close": round(float(nifty[i]), 2),
            "change_pct": round(float(market[i] * 100), 3),
            "volume": float(int(rng.uniform(2e8, 5e8))),
            "pe": 22.0, "pb": 4.0, "div_yield": 1.2,
            "source": "SYNTHETIC_DEMO", "is_synthetic": 1,
        })

    db.upsert_daily(stock_rows)
    db.upsert_index(index_rows)
    with db.tx() as c:
        c.executemany(
            "INSERT INTO symbols (symbol,sector,in_nifty50,in_nifty200,is_fno)"
            " VALUES (?,?,1,1,1)"
            " ON CONFLICT(symbol) DO UPDATE SET sector=excluded.sector",
            sym_rows)

    db.log_quality("daily_ohlc", "synthetic_dataset_loaded", "WARN",
                   len(stock_rows),
                   "SYNTHETIC demo data loaded. NOT market data. "
                   "Signals are disabled for these rows.")

    return {"stock_rows": len(stock_rows), "index_rows": len(index_rows),
            "symbols": len(UNIVERSE), "days": n,
            "start": dates[0].isoformat(), "end": dates[-1].isoformat()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--seed", type=int, default=20260923)
    a = ap.parse_args()

    print("=" * 78)
    print("GENERATING SYNTHETIC DEMO DATA - THIS IS NOT REAL MARKET DATA")
    print("=" * 78)
    db = Database(a.db)
    stats = build(db, a.days, a.seed)
    for k, v in stats.items():
        print(f"  {k:<12} {v}")
    print("\nAll rows flagged is_synthetic=1. Trading signals are BLOCKED.")
    print("Replace with real data via scripts/bootstrap_data.py once your")
    print("source probe shows a WORKING provider.")


if __name__ == "__main__":
    main()
