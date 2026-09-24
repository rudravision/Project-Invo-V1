"""Corporate action detection and adjustment (spec item 3).

The point of these tests is the distinction that matters: a split must be
adjusted, a genuine crash must be kept and flagged. Getting that backwards
corrupts every indicator downstream.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.corporate_actions import (GAP_THRESHOLD, build_adjusted_series,
                                        detect_events, load_known_actions,
                                        persist_events,
                                        run_corporate_action_pass,
                                        unresolved_report)
from app.db.database import Database
from app.db.migrations import migrate


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "t.sqlite")
    migrate(d, tmp_path / "backups")
    return d


def bars(sym, start, specs):
    """specs: list of (open, high, low, close)."""
    rows, day = [], start
    for o, h, l, c in specs:
        rows.append({"symbol": sym, "date": day.isoformat(), "open": o,
                     "high": h, "low": l, "close": c, "volume": 100_000,
                     "source": "test", "is_synthetic": 0})
        day += dt.timedelta(days=1)
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
    return rows


def quiet(price, n):
    """n calm bars around `price`."""
    return [(price * 0.998, price * 1.006, price * 0.994, price)
            for _ in range(n)]


def split_day(price):
    """A post-split session: the whole day trades at the new scale."""
    return [(price * 1.001, price * 1.008, price * 0.993, price)]


def crash_day(prev_close, close):
    """A genuine crash: opens near the previous close, then collapses.

    The intraday range therefore OVERLAPS the previous day's range, which is
    exactly what a split never does.
    """
    return [(prev_close * 0.99, prev_close * 1.002, close * 0.985, close)]


# --------------------------------------------------------------------------- #
def test_split_is_inferred_not_deleted():
    rows = bars("SPLITCO", dt.date(2025, 1, 6),
                quiet(1000, 4) + split_day(500) + quiet(502, 3))
    ev = detect_events(pd.DataFrame(rows))
    assert len(ev) == 1
    assert ev[0].confidence == "INFERRED"
    assert ev[0].factor == pytest.approx(0.5, abs=0.02)
    assert "1:2" in ev[0].ratio_text


def test_confirmed_action_beats_inference(db):
    rows = bars("BONUSCO", dt.date(2025, 2, 3),
                quiet(900, 3) + split_day(300) + quiet(301, 3))
    db.upsert_daily(rows)
    ex = rows[3]["date"]
    with db.tx() as c:
        c.execute("INSERT INTO corporate_actions (symbol,ex_date,action_type,"
                  "ratio_from,ratio_to,details,source) VALUES"
                  " ('BONUSCO',?,'SPLIT',1,3,'1:3 split','test')", (ex,))
    ev = detect_events(pd.DataFrame(rows), load_known_actions(db))
    assert len(ev) == 1
    assert ev[0].confidence == "CONFIRMED"
    assert ev[0].factor == pytest.approx(1 / 3, abs=0.02)


def test_genuine_crash_is_flagged_not_adjusted():
    """-26% with an overlapping intraday range: a real move, never adjusted."""
    rows = bars("CRASHCO", dt.date(2025, 3, 3),
                quiet(500, 4) + crash_day(505, 374) + quiet(370, 2))
    ev = detect_events(pd.DataFrame(rows))
    assert len(ev) == 1
    assert ev[0].confidence == "UNRESOLVED"
    assert ev[0].factor == 1.0, "an unexplained move must be left at scale 1.0"


def test_odd_ratio_crash_is_unresolved():
    """A drop that matches no standard ratio is never guessed at."""
    rows = bars("ODDCO", dt.date(2025, 3, 3),
                quiet(800, 3) + crash_day(800, 611) + quiet(608, 2))
    ev = detect_events(pd.DataFrame(rows))
    assert len(ev) == 1
    assert ev[0].confidence == "UNRESOLVED"


def test_small_moves_ignored():
    rows = bars("CALMCO", dt.date(2025, 4, 1),
                quiet(100, 3) + [(103, 112, 102, 111)] + quiet(110, 2))
    assert detect_events(pd.DataFrame(rows)) == []


def test_adjustment_makes_series_continuous(db):
    rows = bars("ADJCO", dt.date(2025, 1, 6),
                quiet(1000, 4) + split_day(500) + quiet(503, 3))
    db.upsert_daily(rows)
    persist_events(db, detect_events(pd.DataFrame(rows)))
    res = build_adjusted_series(db, ["ADJCO"])
    assert res["adjusted_symbols"] == 1

    conn = db.connect()
    adj = pd.read_sql_query(
        "SELECT date, close, volume, adj_factor FROM daily_ohlc_adjusted"
        " WHERE symbol='ADJCO' ORDER BY date", conn)
    raw = pd.read_sql_query(
        "SELECT date, close, volume FROM daily_ohlc WHERE symbol='ADJCO'"
        " ORDER BY date", conn)
    conn.close()

    jump = adj["close"].pct_change().abs().max()
    assert jump < GAP_THRESHOLD, f"a {jump:.1%} jump survived adjustment"
    # pre-event bars halved, volume doubled, raw untouched
    assert adj["close"].iloc[0] == pytest.approx(500, abs=1)
    assert adj["volume"].iloc[0] == pytest.approx(200_000, rel=0.01)
    assert raw["close"].iloc[0] == 1000
    assert raw["volume"].iloc[0] == 100_000


def test_unresolved_event_leaves_prices_alone(db):
    rows = bars("FLAGCO", dt.date(2025, 6, 2),
                quiet(500, 4) + crash_day(505, 374) + quiet(370, 2))
    db.upsert_daily(rows)
    run_corporate_action_pass(db)

    rep = unresolved_report(db)
    assert "FLAGCO" in set(rep["symbol"]), "the unexplained move must be flagged"

    conn = db.connect()
    adj = pd.read_sql_query(
        "SELECT close, adj_factor FROM daily_ohlc_adjusted"
        " WHERE symbol='FLAGCO' ORDER BY date", conn)
    conn.close()
    assert (adj["adj_factor"] == 1.0).all(), "unresolved events must not adjust"
    assert adj["close"].iloc[0] == pytest.approx(500, abs=1)


def test_raw_prices_are_never_modified(db):
    rows = bars("RAWCO", dt.date(2025, 5, 5),
                quiet(800, 3) + split_day(400) + quiet(402, 2))
    db.upsert_daily(rows)
    q = "SELECT close FROM daily_ohlc WHERE symbol='RAWCO' ORDER BY date"
    before = db.connect().execute(q).fetchall()
    run_corporate_action_pass(db)
    after = db.connect().execute(q).fetchall()
    assert [r[0] for r in before] == [r[0] for r in after]


def test_pass_is_idempotent(db):
    db.upsert_daily(bars("IDEMCO", dt.date(2025, 7, 7),
                         quiet(1000, 3) + split_day(500) + quiet(502, 2)))
    first = run_corporate_action_pass(db)
    second = run_corporate_action_pass(db)
    assert first["detected"] == second["detected"] == 1
    conn = db.connect()
    n = conn.execute("SELECT COUNT(*) FROM adjustment_factors"
                     " WHERE symbol='IDEMCO'").fetchone()[0]
    rows = conn.execute("SELECT COUNT(*) FROM daily_ohlc_adjusted"
                        " WHERE symbol='IDEMCO'").fetchone()[0]
    conn.close()
    assert n == 1, "re-running must not duplicate adjustment factors"
    assert rows == 6, "re-running must not duplicate adjusted price rows"


def test_no_data_is_handled():
    assert detect_events(pd.DataFrame()) == []
