"""
End-to-end proof that the repair fixes the reported failure.

The real NSE endpoints are unreachable from the build environment, so the
provider is stubbed with a source that behaves the way NSE does:
  * publishes a bhavcopy on genuine trading sessions
  * raises NotAvailableError (HTTP 404) on holidays
  * fails intermittently, the way a flaky network does

That is enough to exercise every branch of the sync loop: retry, resume,
holiday inference, and index backfill.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.base import NotAvailableError
from app.data.calendar import HOLIDAY, SESSION, MarketCalendar
from app.data.repair import DownloadQueue, analyse_gaps
from app.db.database import Database
from app.db.migrations import migrate

SYMBOLS = [f"STK{i:03d}" for i in range(40)]
HOLIDAYS = {dt.date(2026, 8, 15), dt.date(2026, 9, 7)}


def sessions_in(start: dt.date, end: dt.date) -> list[dt.date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5 and d not in HOLIDAYS:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


class StubNSE:
    """Behaves like the real archive provider, deterministically."""

    name = "stub_nse"

    def __init__(self, fail_dates=None, fail_times=1):
        self.fail_dates = dict.fromkeys(fail_dates or [], fail_times)
        self.calls = []

    def bhavcopy(self, d: dt.date):
        self.calls.append(d)
        if d in HOLIDAYS or d.weekday() >= 5:
            raise NotAvailableError(f"404 not published: {d}")
        if self.fail_dates.get(d, 0) > 0:
            self.fail_dates[d] -= 1
            raise ConnectionError("transient network error")
        return [{"SctySrs": "EQ", "TckrSymb": s, "OpnPric": "100.0",
                 "HghPric": "101.0", "LwPric": "99.0", "ClsPric": "100.5",
                 "PrvsClsgPric": "100.0", "TtlTradgVol": "500000",
                 "TtlTrfVal": "50000000", "TtlNbOfTxsExctd": "2000",
                 "ISIN": f"INE{hash(s) % 10**9:09d}"} for s in SYMBOLS]

    def get_index_ohlc(self, names, start, end):
        import pandas as pd
        if start in HOLIDAYS or start.weekday() >= 5:
            raise NotAvailableError("closed")
        return pd.DataFrame([
            {"symbol": n, "date": start, "open": 20000.0, "high": 20100.0,
             "low": 19900.0, "close": 20050.0, "change_pct": 0.25,
             "volume": 1e7, "pe": 22.0, "pb": 4.0, "div_yield": 1.2}
            for n in ("NIFTY 50", "NIFTY BANK", "NIFTY IT")])

    def get_index_membership(self, slug):
        import pandas as pd
        return pd.DataFrame([{"symbol": s, "company_name": s,
                              "isin_code": "X", "industry": "Test"}
                             for s in SYMBOLS])

    def get_trading_calendar(self, year):
        import pandas as pd
        return pd.DataFrame([{"date": pd.Timestamp(h), "description": "Holiday",
                              "segment": "CM"} for h in HOLIDAYS
                             if h.year == year])

    def get_delivery(self, d):
        raise NotAvailableError("no delivery in stub")

    def health_check(self):
        return True, "stub"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    dbp = tmp_path / "t.sqlite"
    db = Database(dbp)
    migrate(db, tmp_path / "bk")

    class S:
        backups_dir = tmp_path / "bk"
        logs_dir = tmp_path / "logs"
        raw_dir = tmp_path / "raw"
        db_path = dbp

        @staticmethod
        def source_defaults():
            return {}
    S.logs_dir.mkdir(exist_ok=True)
    return db, S


def _patch(monkeypatch, stub):
    import scripts.sync_data as sd
    monkeypatch.setattr(sd, "NSEArchiveProvider", lambda *a, **k: stub)
    monkeypatch.setattr(sd, "MEMBERSHIP_SLUGS", ["nifty200"])
    monkeypatch.setattr(sd, "SECTOR_FROM_SLUG", {"nifty200": "Test Sector"})
    return sd


def test_sync_downloads_every_session_and_marks_holidays(env, monkeypatch):
    db, S = env
    stub = StubNSE()
    sd = _patch(monkeypatch, stub)
    monkeypatch.setattr(sd, "PERIODS", {"1m": 30})

    stats = sd.run_sync(db, S, period="1m", universe="nifty200",
                        fetch_delivery=False)

    cal = MarketCalendar(db)
    end = dt.date.today()
    start = end - dt.timedelta(days=30)
    expected = sessions_in(start, end)

    assert stats["sessions_downloaded"] == len(expected)
    assert stats["index_days"] == len(expected)
    for h in HOLIDAYS:
        if start <= h <= end:
            assert cal.status(h) == HOLIDAY
    for s in expected:
        assert cal.status(s) == SESSION


def test_sync_retries_transient_failures(env, monkeypatch):
    db, S = env
    end = dt.date.today()
    target = next(d for d in sessions_in(end - dt.timedelta(days=20), end))
    stub = StubNSE(fail_dates=[target], fail_times=1)
    sd = _patch(monkeypatch, stub)
    monkeypatch.setattr(sd, "PERIODS", {"1m": 20})

    sd.run_sync(db, S, period="1m", fetch_delivery=False)   # first pass fails it
    q = DownloadQueue(db)
    assert target.isoformat() in q.pending("cm_bhavcopy")

    sd.run_sync(db, S, period="1m", fetch_delivery=False)   # retry succeeds
    assert MarketCalendar(db).status(target) == SESSION


def test_sync_is_incremental_second_run_downloads_nothing(env, monkeypatch):
    db, S = env
    stub = StubNSE()
    sd = _patch(monkeypatch, stub)
    monkeypatch.setattr(sd, "PERIODS", {"1m": 25})

    first = sd.run_sync(db, S, period="1m", fetch_delivery=False)
    n_calls = len(stub.calls)
    second = sd.run_sync(db, S, period="1m", fetch_delivery=False)

    assert first["sessions_downloaded"] > 0
    assert second["sessions_downloaded"] == 0
    assert len(stub.calls) == n_calls        # no repeat downloads


def test_sync_can_be_stopped_and_resumed(env, monkeypatch):
    db, S = env
    stub = StubNSE()
    sd = _patch(monkeypatch, stub)
    monkeypatch.setattr(sd, "PERIODS", {"1m": 30})

    seen = {"n": 0}

    def stop_after_3():
        seen["n"] += 1
        return seen["n"] > 3

    part = sd.run_sync(db, S, period="1m", fetch_delivery=False,
                       should_stop=stop_after_3)
    assert part["stopped_early"] is True

    full = sd.run_sync(db, S, period="1m", fetch_delivery=False)
    gap = analyse_gaps(db)
    assert gap.problems == 0, gap.summary()


def test_after_sync_there_are_no_data_problems(env, monkeypatch):
    db, S = env
    stub = StubNSE()
    sd = _patch(monkeypatch, stub)
    monkeypatch.setattr(sd, "PERIODS", {"2m": 60})

    sd.run_sync(db, S, period="2m", fetch_delivery=False)
    gap = analyse_gaps(db)

    assert gap.problems == 0, gap.summary()
    assert gap.total_present == gap.total_expected
    assert gap.counts.get("UNVERIFIED_DATE", 0) == 0


def test_index_data_is_populated(env, monkeypatch):
    """Directly addresses 'No index data available to build a heatmap'."""
    db, S = env
    sd = _patch(monkeypatch, StubNSE())
    monkeypatch.setattr(sd, "PERIODS", {"1m": 30})
    sd.run_sync(db, S, period="1m", fetch_delivery=False)

    conn = db.connect()
    try:
        n = conn.execute("SELECT COUNT(*) FROM index_ohlc").fetchone()[0]
        idx = conn.execute(
            "SELECT COUNT(DISTINCT index_name) FROM index_ohlc").fetchone()[0]
    finally:
        conn.close()
    assert n > 0 and idx == 3


def test_sector_mapping_is_populated(env, monkeypatch):
    db, S = env
    sd = _patch(monkeypatch, StubNSE())
    monkeypatch.setattr(sd, "PERIODS", {"1m": 20})
    sd.run_sync(db, S, period="1m", fetch_delivery=False)

    conn = db.connect()
    try:
        n = conn.execute("SELECT COUNT(*) FROM symbols WHERE sector IS NOT NULL"
                         ).fetchone()[0]
        m = conn.execute("SELECT COUNT(*) FROM index_membership").fetchone()[0]
    finally:
        conn.close()
    assert n == len(SYMBOLS)
    assert m == len(SYMBOLS)


def test_validator_passes_after_repair(env, monkeypatch):
    import pandas as pd

    from app.data.quality2 import validate_daily_v2
    db, S = env
    sd = _patch(monkeypatch, StubNSE())
    monkeypatch.setattr(sd, "PERIODS", {"3m": 90})
    sd.run_sync(db, S, period="3m", fetch_delivery=False)

    conn = db.connect()
    try:
        df = pd.read_sql_query(
            "SELECT symbol,date,open,high,low,close,volume,is_synthetic"
            " FROM daily_ohlc", conn)
    finally:
        conn.close()

    rep = validate_daily_v2(df, db)
    assert rep.ok, rep.summary()
