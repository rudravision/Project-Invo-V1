"""
End-to-end execution of the buttons.

Why this file exists: the first build of the GUI shipped a crash on the very
first click of UPDATE & ANALYZE MARKET --

    TypeError: MarketCalendar.summary() missing 2 required positional
               arguments: 'start' and 'end'

The API tests all passed, because none of them ever *ran* the update chain.
Three more wrong calls were hiding behind that one (`gap.start`, `gap.end`,
and a bad `DownloadQueue.enqueue` signature in the repair job).

These tests execute the real job functions against a stubbed NSE, so every
call inside them is actually made. A signature mistake anywhere in the chain
fails here instead of on the user's screen.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import load_settings
from app.data.calendar import SESSION, MarketCalendar
from app.db.database import Database
from app.db.migrations import migrate
from app.gui.jobs import Job
from app.gui.pipeline import (build_calibration_job, full_update_job,
                              repair_job, run_backtest_job)
from app.analytics.recommend import RiskSettings

from test_sync_integration import HOLIDAYS, StubNSE, sessions_in  # reuse


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A real settings object on a temp root, with NSE stubbed out."""
    import shutil
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    for f in (ROOT / "config").glob("*.yaml"):
        shutil.copy(f, root / "config" / f.name)

    settings = load_settings(str(root))
    db = Database(settings.db_path)
    migrate(db, settings.backups_dir)

    stub = StubNSE()
    import scripts.sync_data as sd
    monkeypatch.setattr(sd, "NSEArchiveProvider", lambda *a, **k: stub)
    monkeypatch.setattr(sd, "MEMBERSHIP_SLUGS", ["nifty200"])
    monkeypatch.setattr(sd, "SECTOR_FROM_SLUG", {"nifty200": "Test Sector"})
    monkeypatch.setattr(sd, "PERIODS", {"3m": 90, "5y": 90, "max": 90})
    return db, settings, stub


def job():
    return Job(id="test", name="test")


# --------------------------------------------------------------------------- #
def test_update_job_runs_the_whole_chain(env):
    """The exact click that crashed. It must complete every step."""
    db, settings, _ = env
    j = job()

    out = full_update_job(j, db, settings, period="3m", universe="nifty200",
                          risk=RiskSettings())

    assert j.status == "running", "the job itself must not have errored"
    # every one of the 11 steps was reached
    assert j.current == j.total == 11, f"stopped at step {j.current}: {j.message}"

    # the step that crashed before
    assert "calendar" in out
    assert isinstance(out["calendar"], dict)

    assert out["rows"] > 0, "no prices were downloaded"
    assert out["symbols"] > 0
    assert "quality_ok" in out
    assert "corporate_actions" in out
    assert out["indices"] > 0, "index data must be downloaded"
    assert "calibration" in out
    assert "recommendations" in out
    assert out["report_file"].startswith("market_update_")
    assert (settings.reports_dir / out["report_file"]).exists()


def test_update_job_reports_progress_for_every_step(env):
    db, settings, _ = env
    j = job()
    full_update_job(j, db, settings, period="3m")
    assert j.total == 11
    assert j.percent == 100
    # the user must have seen readable progress, not silence
    assert len(j.steps) >= 11
    assert any("Downloading" in s for s in j.steps)
    assert any("Backing up" in s for s in j.steps)


def test_update_job_takes_a_backup_before_touching_anything(env):
    db, settings, _ = env
    out = full_update_job(job(), db, settings, period="3m")
    assert "backup" in out, out.get("backup_error")
    assert (settings.backups_dir / out["backup"]).exists()


def test_update_job_can_be_cancelled_midway(env):
    db, settings, _ = env
    j = job()
    j._cancel.set()                      # user pressed Stop immediately
    out = full_update_job(j, db, settings, period="3m")
    assert j.current < 11, "cancellation must stop the chain early"
    assert "recommendations" not in out


def test_update_job_is_incremental_on_second_run(env):
    db, settings, stub = env
    full_update_job(job(), db, settings, period="3m")
    first_calls = len(stub.calls)
    stub.calls.clear()
    full_update_job(job(), db, settings, period="3m")
    assert first_calls > 0
    assert len(stub.calls) < first_calls / 2, \
        "the second run re-downloaded data it already had"


def test_repair_job_runs_end_to_end(env):
    """Covers gap.start / gap.end / enqueue - all wrong in the first build."""
    db, settings, _ = env
    j = job()
    out = repair_job(j, db, settings)

    assert j.current == j.total == 6, f"stopped at: {j.message}"
    assert isinstance(out["before"], str)
    assert isinstance(out["after"], str)
    assert "plan" in out
    assert set(out["plan"]) == {"refetch_sessions", "verify_dates",
                                "need_index"}
    assert "quality" in out


def test_repair_job_actually_fixes_a_hole(env):
    """Delete a session's bars, then prove the repair puts them back."""
    db, settings, _ = env
    full_update_job(job(), db, settings, period="3m")

    conn = db.connect()
    victim = conn.execute(
        "SELECT date FROM daily_ohlc GROUP BY date ORDER BY date DESC"
        " LIMIT 1 OFFSET 5").fetchone()[0]
    before = conn.execute("SELECT COUNT(*) FROM daily_ohlc").fetchone()[0]
    conn.close()
    with db.tx() as c:
        c.execute("DELETE FROM daily_ohlc WHERE date=?", (victim,))
    holed = db.connect().execute("SELECT COUNT(*) FROM daily_ohlc").fetchone()[0]
    assert holed < before

    repair_job(job(), db, settings)

    after = db.connect().execute(
        "SELECT COUNT(*) FROM daily_ohlc WHERE date=?", (victim,)).fetchone()[0]
    assert after > 0, "the repair did not restore the deleted session"
    assert MarketCalendar(db).status(dt.date.fromisoformat(victim)) == SESSION


def test_calibration_job_refuses_without_enough_history(env):
    """Honesty check: a short history must not produce probabilities."""
    db, settings, _ = env
    full_update_job(job(), db, settings, period="3m")
    out = build_calibration_job(job(), db, settings)
    assert out["built"] is False
    assert "Insufficient data" in out["message"] or \
        "not enough history" in out["message"].lower()


def test_calibration_job_errors_clearly_on_empty_database(env):
    db, settings, _ = env
    with pytest.raises(ValueError, match="No real market data"):
        build_calibration_job(job(), db, settings)


def test_backtest_job_refuses_short_history(env):
    db, settings, _ = env
    full_update_job(job(), db, settings, period="3m")
    with pytest.raises(ValueError, match="sessions available"):
        run_backtest_job(job(), db, settings, {})


def test_backtest_job_errors_clearly_on_empty_database(env):
    db, settings, _ = env
    with pytest.raises(ValueError, match="no real market data"):
        run_backtest_job(job(), db, settings, {})


def test_update_job_populates_sectors_and_membership(env):
    db, settings, _ = env
    full_update_job(job(), db, settings, period="3m")
    conn = db.connect()
    sectors = conn.execute(
        "SELECT COUNT(*) FROM symbols WHERE sector IS NOT NULL").fetchone()[0]
    members = conn.execute(
        "SELECT COUNT(*) FROM index_membership").fetchone()[0]
    conn.close()
    assert sectors > 0, "no stock got a sector"
    assert members > 0, "index membership was not recorded"


def test_update_job_survives_a_download_failure(env, monkeypatch):
    """A broken source must be reported, not crash the whole run."""
    db, settings, _ = env
    import scripts.sync_data as sd
    monkeypatch.setattr(sd, "run_sync",
                        lambda *a, **k: (_ for _ in ()).throw(
                            ConnectionError("network down")))
    j = job()
    out = full_update_job(j, db, settings, period="3m")
    assert "sync_error" in out
    assert any("failed" in s.lower() for s in j.steps)
