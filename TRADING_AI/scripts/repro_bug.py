#!/usr/bin/env python3
"""
Reproduce the user's reported failure so the root cause is proven, not guessed.

Reported symptom (real run on G:\\Trading\\TRADING_AI):
    Data quality: daily_ohlc | rows=9000 | FAIL
    [ERROR] missing_candles: 7600
    No index data available to build a heatmap.
    No stocks passed the liquidity/history filters.

This script rebuilds that exact situation from the OLD downloader's behaviour:
a 120-calendar-day window where only some sessions were successfully fetched,
with no record of which days were genuine NSE sessions.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from app.db.database import Database


def build(db_path: Path, n_symbols: int = 200, window_days: int = 120,
          success_ratio: float = 0.52, seed: int = 11) -> dict:
    rng = np.random.default_rng(seed)
    db = Database(db_path)

    end = dt.date(2026, 9, 22)
    start = end - dt.timedelta(days=window_days)

    weekdays = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            weekdays.append(d)
        d += dt.timedelta(days=1)

    # The old downloader skipped any day whose HTTP fetch failed and never
    # came back for it -> a sparse, discontinuous scatter of sessions.
    n_ok = int(len(weekdays) * success_ratio)
    got = sorted(rng.choice(len(weekdays), size=n_ok, replace=False).tolist())
    fetched = [weekdays[i] for i in got]

    symbols = [f"STK{i:03d}" for i in range(n_symbols)]
    rows = []
    for s in symbols:
        px = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, len(fetched))))
        for i, day in enumerate(fetched):
            o = float(px[i] * (1 + rng.normal(0, 0.003)))
            rows.append({
                "symbol": s, "date": day.isoformat(),
                "open": round(o, 2),
                "high": round(max(o, px[i]) * 1.008, 2),
                "low": round(min(o, px[i]) * 0.992, 2),
                "close": round(float(px[i]), 2),
                "prev_close": None,
                "volume": float(rng.integers(200_000, 4_000_000)),
                "turnover": None, "trades": None,
                "source": "nse_archive", "is_synthetic": 0,
            })
    db.upsert_daily(rows)

    return {
        "weekdays_in_window": len(weekdays),
        "sessions_fetched": len(fetched),
        "sessions_skipped": len(weekdays) - len(fetched),
        "symbols": n_symbols,
        "rows": len(rows),
        "index_rows": 0,
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1
               else "/tmp/repro/trading_ai.sqlite")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    stats = build(out)
    print("=" * 74)
    print("REPRODUCING THE REPORTED FAILURE")
    print("=" * 74)
    for k, v in stats.items():
        print(f"  {k:<22} {v}")

    import pandas as pd

    from app.data.quality import gate_signal, validate_daily

    db = Database(out)
    conn = db.connect()
    try:
        df = pd.read_sql_query(
            "SELECT symbol,date,open,high,low,close,volume,is_synthetic"
            " FROM daily_ohlc", conn)
    finally:
        conn.close()

    rep = validate_daily(df)
    print()
    print(rep.summary())
    allowed, msg = gate_signal(rep, is_synthetic=False)
    print(f"\nSIGNAL GATE: {'ALLOWED' if allowed else 'BLOCKED'}")
    print(msg)
    print(f"\nDatabase written to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
