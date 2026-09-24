"""Build a stand-in for a real downloaded database, for manual testing.

This exists because several bugs only appeared at realistic scale and with
the real NSE index spelling: mixed-case index names, a few unadjusted stock
splits, and a couple of years of sessions.

    python tests/tools/make_repro_db.py [target_dir]

It writes a throwaway TRADING_AI root (default: a temp directory) and prints
the path. The prices are invented. Never point the app at this for trading
decisions - it is a test fixture, not market data.
"""
from __future__ import annotations

import datetime as dt
import math
import pathlib
import random
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
APP_ROOT = HERE.parents[2]
sys.path.insert(0, str(APP_ROOT))

N_STOCKS = 120
N_SESSIONS = 500

# Real NSE spelling, including the thematic indices that are not sectors.
INDICES = [
    "Nifty 50", "Nifty 100", "Nifty 200", "Nifty Next 50",
    "Nifty Bank", "Nifty IT", "Nifty Auto", "Nifty Pharma", "Nifty Metal",
    "Nifty Realty", "Nifty FMCG", "Nifty Energy", "Nifty Healthcare Index",
    "Nifty Financial Services", "Nifty PSU Bank", "Nifty Private Bank",
    "Nifty Media", "Nifty Consumer Durables",
    "Nifty IPO", "SME EMERGE", "Nifty Microcap 250", "Nifty500 Growth 50",
]
SECTORS = ["Bank", "IT", "Auto", "Pharma", "Metal", "Realty", "FMCG",
           "Energy"]


def build(root: pathlib.Path, seed: int = 7) -> pathlib.Path:
    if root.exists():
        shutil.rmtree(root)
    (root / "config").mkdir(parents=True)
    for f in (APP_ROOT / "config").glob("*.yaml"):
        shutil.copy(f, root / "config" / f.name)

    from app.data.calendar import MarketCalendar, SymbolLifecycle
    from app.gui.server import create_app

    app = create_app(str(root))
    db = app.config["DB"]
    rng = random.Random(seed)

    end = dt.date.today() - dt.timedelta(days=1)
    while end.weekday() >= 5:
        end -= dt.timedelta(days=1)
    days, d = [], end - dt.timedelta(days=int(N_SESSIONS * 1.45))
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    days = days[-N_SESSIONS:]

    cal = MarketCalendar(db)
    cal.seed_weekends(days[0], days[-1])
    for x in days:
        cal.mark(x, "SESSION", evidence="repro-fixture", source="test")

    names = [f"STK{i:03d}" for i in range(N_STOCKS)]
    with db.tx() as c:
        c.executemany(
            "INSERT OR REPLACE INTO symbols (symbol,sector,in_nifty200)"
            " VALUES (?,?,1)",
            [(n, SECTORS[i % len(SECTORS)]) for i, n in enumerate(names)])

    # Two stocks carry an unadjusted split, like the user's real data.
    splits = {names[5]: 0.5, names[40]: 0.2}
    rows = []
    for i, n in enumerate(names):
        p = 80 + (i * 37) % 3000
        drift = 0.0006 * math.sin(i) + 0.0002
        for k, x in enumerate(days):
            p *= math.exp(drift + 0.012 * rng.gauss(0, 1))
            if n in splits and k == len(days) - 60:
                p *= splits[n]
            rows.append({"symbol": n, "date": x.isoformat(), "open": p * 0.996,
                         "high": p * 1.012, "low": p * 0.988, "close": p,
                         "volume": rng.randint(200_000, 5_000_000),
                         "source": "repro", "is_synthetic": 0})
    db.upsert_daily(rows)

    irows = []
    for j, nm in enumerate(INDICES):
        v = 8000 + j * 900
        dr = 0.0009 - 0.00022 * j
        for k, x in enumerate(days):
            v *= math.exp(dr + 0.007 * math.sin(k / 11 + j)
                          + 0.004 * rng.gauss(0, 1))
            irows.append({"index_name": nm, "date": x.isoformat(), "open": v,
                          "high": v * 1.004, "low": v * 0.996, "close": v,
                          "change_pct": 0.0, "source": "repro",
                          "is_synthetic": 0})
    db.upsert_index(irows)
    SymbolLifecycle(db).rebuild()
    return root


if __name__ == "__main__":
    target = (pathlib.Path(sys.argv[1]) if len(sys.argv) > 1
              else pathlib.Path(tempfile.mkdtemp(prefix="trading_ai_repro_")))
    out = build(target)
    print(f"built {N_STOCKS} stocks x {N_SESSIONS} sessions, "
          f"{len(INDICES)} indices at {out}")
