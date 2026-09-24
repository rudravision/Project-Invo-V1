"""
Tests for the data-repair layer.

The central regression these lock down: the system must NOT report a missing
candle for a day it never attempted, for a stock that had not listed, for a
stock that was suspended, or for a day the exchange was shut.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.calendar import (HOLIDAY, SESSION, UNKNOWN, WEEKEND,
                               MarketCalendar, SymbolLifecycle)
from app.data.repair import DownloadQueue, analyse_gaps, plan_repair
from app.db.database import Database
from app.db.migrations import migrate, pending


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "t.sqlite")
    migrate(d, tmp_path / "bk")
    return d


def add_bars(db, symbol, dates, price=100.0):
    db.upsert_daily([{
        "symbol": symbol, "date": d if isinstance(d, str) else d.isoformat(),
        "open": price, "high": price * 1.01, "low": price * 0.99,
        "close": price, "volume": 500_000.0, "source": "test",
        "is_synthetic": 0} for d in dates])


# ------------------------------------------------------------- migrations --
def test_migrations_are_idempotent(tmp_path):
    d = Database(tmp_path / "m.sqlite")
    r1 = migrate(d, tmp_path / "bk")
    # every migration defined in the module must run on a fresh database
    from app.db.migrations import MIGRATIONS
    assert r1["applied"] == [name for name, _ in MIGRATIONS]
    r2 = migrate(d, tmp_path / "bk")
    assert r2["applied"] == []
    assert pending(d) == []


def test_migration_takes_verified_backup(tmp_path):
    d = Database(tmp_path / "m.sqlite")
    add_bars(d, "AAA", ["2026-01-05"])
    res = migrate(d, tmp_path / "bk")
    assert res["backup"] is not None
    assert Path(res["backup"]).exists()
    assert all(b["ok"] for b in d.verify_backups(tmp_path / "bk"))


def test_migration_preserves_existing_data(tmp_path):
    d = Database(tmp_path / "m.sqlite")
    add_bars(d, "AAA", ["2026-01-05", "2026-01-06"])
    migrate(d, tmp_path / "bk")
    assert d.coverage()["rows"] == 2


# ---------------------------------------------------------------- calendar --
def test_weekend_is_never_a_session(db):
    cal = MarketCalendar(db)
    cal.seed_weekends(dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert cal.status(dt.date(2026, 9, 5)) == WEEKEND   # Saturday
    assert cal.status(dt.date(2026, 9, 6)) == WEEKEND   # Sunday


def test_unknown_is_the_honest_default(db):
    cal = MarketCalendar(db)
    # A weekday we have said nothing about must be UNKNOWN, not SESSION.
    assert cal.status(dt.date(2026, 9, 8)) == UNKNOWN


def test_sessions_inferred_from_price_data(db):
    days = ["2026-09-07", "2026-09-08", "2026-09-09"]
    for i in range(30):
        add_bars(db, f"S{i:02d}", days)
    cal = MarketCalendar(db)
    assert cal.infer_sessions_from_data(min_symbols=20) == 3
    assert cal.status("2026-09-08") == SESSION


def test_holiday_marking(db):
    cal = MarketCalendar(db)
    cal.load_holidays([dt.date(2026, 10, 2)])
    assert cal.status(dt.date(2026, 10, 2)) == HOLIDAY


def test_session_is_never_downgraded(db):
    cal = MarketCalendar(db)
    cal.mark("2026-09-08", SESSION, bhavcopy=True)
    cal.mark("2026-09-08", UNKNOWN)
    assert cal.status("2026-09-08") == SESSION


def test_unknown_between_excludes_weekends_and_known(db):
    cal = MarketCalendar(db)
    cal.seed_weekends(dt.date(2026, 9, 7), dt.date(2026, 9, 13))
    cal.mark("2026-09-07", SESSION, bhavcopy=True)
    unk = cal.unknown_between(dt.date(2026, 9, 7), dt.date(2026, 9, 13))
    assert dt.date(2026, 9, 7) not in unk       # known session
    assert dt.date(2026, 9, 12) not in unk      # Saturday
    assert dt.date(2026, 9, 8) in unk           # genuinely unchecked


# --------------------------------------------------------------- lifecycle --
def test_lifecycle_detects_active(db):
    days = ["2026-09-07", "2026-09-08", "2026-09-09"]
    for i in range(25):
        add_bars(db, f"S{i:02d}", days)
    MarketCalendar(db).infer_sessions_from_data()
    out = SymbolLifecycle(db).rebuild()
    assert out["active"] == 25


# ------------------------------------------------------- gap classification --
def test_new_listing_is_not_missing_data(db):
    """A stock that listed late must not show the earlier days as missing."""
    sessions = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]
    for i in range(25):
        add_bars(db, f"OLD{i:02d}", sessions)
    add_bars(db, "NEWCO", sessions[2:])          # listed on day 3

    MarketCalendar(db).infer_sessions_from_data()
    SymbolLifecycle(db).rebuild()
    gap = analyse_gaps(db)

    assert gap.by_symbol["NEWCO"]["NOT_YET_LISTED"] == 2
    assert gap.by_symbol["NEWCO"].get("SOURCE_NOT_FETCHED", 0) == 0


def test_not_traded_when_bhavcopy_held(db):
    """We have the day's file and the stock simply is not in it."""
    sessions = ["2026-09-01", "2026-09-02", "2026-09-03"]
    for i in range(25):
        add_bars(db, f"S{i:02d}", sessions)
    add_bars(db, "ILLIQ", ["2026-09-01", "2026-09-03"])   # no trade on the 2nd

    cal = MarketCalendar(db)
    cal.infer_sessions_from_data()
    for s in sessions:
        cal.mark(s, SESSION, bhavcopy=True)
    SymbolLifecycle(db).rebuild()

    gap = analyse_gaps(db)
    assert gap.by_symbol["ILLIQ"]["NOT_TRADED"] == 1
    assert gap.by_symbol["ILLIQ"].get("SOURCE_NOT_FETCHED", 0) == 0


def test_never_fetched_day_is_flagged_repairable(db):
    """A confirmed session with no bhavcopy on file IS a real problem."""
    sessions = ["2026-09-01", "2026-09-02"]
    for i in range(25):
        add_bars(db, f"S{i:02d}", sessions)
    cal = MarketCalendar(db)
    cal.infer_sessions_from_data()
    # Third session known to exist (e.g. from the index file) but never fetched.
    cal.mark("2026-09-03", SESSION, bhavcopy=False, index=True)
    SymbolLifecycle(db).rebuild()

    gap = analyse_gaps(db)
    assert gap.counts["SOURCE_NOT_FETCHED"] == 25
    assert "2026-09-03" in gap.repairable_dates


def test_holiday_never_counted_as_missing(db):
    sessions = ["2026-09-01", "2026-09-03"]
    for i in range(25):
        add_bars(db, f"S{i:02d}", sessions)
    cal = MarketCalendar(db)
    cal.infer_sessions_from_data()
    cal.load_holidays([dt.date(2026, 9, 2)])
    SymbolLifecycle(db).rebuild()

    gap = analyse_gaps(db)
    assert gap.counts.get("SOURCE_NOT_FETCHED", 0) == 0
    assert gap.problems == 0


def test_unverified_counted_once_per_date_not_per_symbol(db):
    """The old code inflated a 2-day gap into 2 x n_symbols."""
    sessions = ["2026-09-07", "2026-09-10"]
    for i in range(50):
        add_bars(db, f"S{i:02d}", sessions)
    cal = MarketCalendar(db)
    cal.seed_weekends(dt.date(2026, 9, 7), dt.date(2026, 9, 10))
    cal.infer_sessions_from_data()
    SymbolLifecycle(db).rebuild()

    gap = analyse_gaps(db)
    # 8th and 9th are unchecked weekdays -> exactly 2, not 2 * 50.
    assert gap.counts["UNVERIFIED_DATE"] == 2


def test_full_coverage_reports_no_problems(db):
    sessions = ["2026-09-01", "2026-09-02", "2026-09-03"]
    for i in range(25):
        add_bars(db, f"S{i:02d}", sessions)
    cal = MarketCalendar(db)
    cal.seed_weekends(dt.date(2026, 9, 1), dt.date(2026, 9, 3))
    cal.infer_sessions_from_data()
    for s in sessions:
        cal.mark(s, SESSION, bhavcopy=True)
    SymbolLifecycle(db).rebuild()

    gap = analyse_gaps(db)
    assert gap.problems == 0
    assert gap.total_present == gap.total_expected


# ------------------------------------------------------------------- queue --
def test_queue_resumes_after_interruption(db):
    q = DownloadQueue(db)
    q.enqueue("cm_bhavcopy", ["2026-09-01", "2026-09-02", "2026-09-03"])
    assert len(q.pending("cm_bhavcopy")) == 3
    q.mark("cm_bhavcopy", "2026-09-01", "DONE")
    remaining = q.pending("cm_bhavcopy")
    assert "2026-09-01" not in remaining
    assert len(remaining) == 2


def test_queue_retries_failures_up_to_limit(db):
    q = DownloadQueue(db)
    q.enqueue("cm_bhavcopy", ["2026-09-01"])
    for _ in range(3):
        q.mark("cm_bhavcopy", "2026-09-01", "FAILED", "boom")
    assert q.pending("cm_bhavcopy", max_attempts=3) == []
    assert q.reset_failed("cm_bhavcopy") == 1
    assert q.pending("cm_bhavcopy", max_attempts=3) == ["2026-09-01"]


def test_queue_does_not_requeue_done(db):
    q = DownloadQueue(db)
    q.enqueue("cm_bhavcopy", ["2026-09-01"])
    q.mark("cm_bhavcopy", "2026-09-01", "DONE")
    q.enqueue("cm_bhavcopy", ["2026-09-01"])
    assert q.pending("cm_bhavcopy") == []


# ------------------------------------------------------------------- plan ---
def test_plan_lists_index_gaps(db):
    sessions = ["2026-09-01", "2026-09-02"]
    for i in range(25):
        add_bars(db, f"S{i:02d}", sessions)
    MarketCalendar(db).infer_sessions_from_data()
    SymbolLifecycle(db).rebuild()
    gap = analyse_gaps(db)
    plan = plan_repair(db, gap, dt.date(2026, 9, 1), dt.date(2026, 9, 2))
    assert set(plan.need_index) == set(sessions)


# --------------------------------------------------------------------------- #
# Regression: the queue must not block repairs
# --------------------------------------------------------------------------- #
def test_requeue_overrides_a_stale_done_marker(db):
    """A date marked DONE whose data has vanished must be fetchable again.

    `enqueue` protects DONE rows so downloads stay incremental. That
    protection also meant a session whose bars were deleted could never be
    re-downloaded: the queue said 'done' while the database sat empty, and
    REPAIR DATA silently did nothing.
    """
    q = DownloadQueue(db)
    q.enqueue("cm_bhavcopy", ["2026-01-05"])
    q.mark("cm_bhavcopy", "2026-01-05", "DONE")
    assert q.pending("cm_bhavcopy") == []

    # enqueue alone must NOT disturb it - that is the incremental guarantee
    q.enqueue("cm_bhavcopy", ["2026-01-05"])
    assert q.pending("cm_bhavcopy") == []

    # requeue is the explicit override
    assert q.requeue("cm_bhavcopy", ["2026-01-05"]) == 1
    assert q.pending("cm_bhavcopy") == ["2026-01-05"]


def test_requeue_does_not_reset_the_attempt_guard(db):
    """A hopeless date must still stop being retried forever."""
    q = DownloadQueue(db)
    q.enqueue("cm_bhavcopy", ["2026-01-06"])
    for _ in range(3):
        q.mark("cm_bhavcopy", "2026-01-06", "FAILED", "boom")
    assert q.pending("cm_bhavcopy", max_attempts=3) == []
    q.requeue("cm_bhavcopy", ["2026-01-06"])
    assert q.pending("cm_bhavcopy", max_attempts=3) == [], \
        "requeue must not wipe the attempt counter"
    assert q.reset_failed("cm_bhavcopy") >= 0


def test_requeue_ignores_unknown_keys(db):
    q = DownloadQueue(db)
    assert q.requeue("cm_bhavcopy", []) == 0
    assert q.requeue("cm_bhavcopy", ["1999-01-01"]) == 0
