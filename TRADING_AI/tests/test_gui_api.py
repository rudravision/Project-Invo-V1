"""GUI server API tests.

Driven through Flask's test client, so these exercise the same code paths the
window uses. The critical behaviour under test: the interface must refuse to
show trade ideas when the data is not trustworthy.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.calendar import MarketCalendar, SymbolLifecycle
from app.db.database import Database
from app.gui.jobs import JobManager, friendly_error
from app.gui.server import create_app


def sessions(start, end):
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def build_root(tmp_path, *, n_syms=12, n_days=260, with_index=True):
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    for f in (ROOT / "config").glob("*.yaml"):
        shutil.copy(f, root / "config" / f.name)
    return root


def seed(app, *, n_syms=12, n_days=260, with_index=True, synthetic=False,
         end=None):
    db = app.config["DB"]
    end = end or dt.date(2025, 9, 19)
    days = sessions(end - dt.timedelta(days=int(n_days * 1.5)), end)[-n_days:]
    cal = MarketCalendar(db)
    cal.seed_weekends(days[0], days[-1])
    for d in days:
        cal.mark(d, "SESSION", evidence="test-seed", source="test")

    sect = ["Bank", "It", "Auto", "Pharma"]
    with db.tx() as c:
        c.executemany("INSERT OR REPLACE INTO symbols (symbol,sector,"
                      "in_nifty200) VALUES (?,?,1)",
                      [(f"T{i:02d}", sect[i % 4]) for i in range(n_syms)])
    rows = []
    for i in range(n_syms):
        p = 100 + i * 25
        for k, d in enumerate(days):
            p *= math.exp(0.0004 * (1 if i % 2 else -1) +
                          0.004 * math.sin(k / 7 + i))
            rows.append({"symbol": f"T{i:02d}", "date": d.isoformat(),
                         "open": p * 0.998, "high": p * 1.008,
                         "low": p * 0.992, "close": p, "volume": 800_000,
                         "source": "test",
                         "is_synthetic": 1 if synthetic else 0})
    db.upsert_daily(rows)

    if with_index:
        irows = []
        for j, name in enumerate(["NIFTY 50", "NIFTY BANK", "NIFTY IT"]):
            v = 20000 + j * 1000
            for k, d in enumerate(days):
                v *= math.exp(0.0005 - 0.0002 * j + 0.003 * math.sin(k / 9))
                irows.append({"index_name": name, "date": d.isoformat(),
                              "open": v, "high": v * 1.003, "low": v * 0.997,
                              "close": v, "change_pct": 0.0, "source": "test",
                              "is_synthetic": 1 if synthetic else 0})
        db.upsert_index(irows)
    SymbolLifecycle(db).rebuild()
    return days


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(build_root(tmp_path)))
    app.config["TESTING"] = True
    return app.test_client(), app


def j(resp):
    return json.loads(resp.data)


# ------------------------------------------------------------- basics -----
def test_index_page_served(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert b"TRADING" in r.data


def test_health(client):
    c, _ = client
    assert j(c.get("/api/health"))["ok"] is True


def test_status_on_empty_database(client):
    c, _ = client
    s = j(c.get("/api/status"))
    assert s["has_data"] is False
    assert s["gate"]["status"] == "blocked"
    assert "UPDATE NOW" in json.dumps(s["gate"])
    assert s["calibration"]["ready"] is False


def test_status_with_data(client):
    c, app = client
    seed(app)
    s = j(c.get("/api/status"))
    assert s["has_data"] is True
    assert s["coverage"]["symbols"] == 12
    assert s["coverage"]["sessions"] > 200
    assert s["breadth"]["total"] == 12
    assert s["nifty"] is not None
    assert s["database"]["healthy"] is True
    assert s["market"] in ("Bullish", "Bearish", "Neutral", "Strong bullish",
                           "Strong bearish", "Unknown")


# ------------------------------------------------- the safety gate --------
def test_recommendations_blocked_without_data(client):
    c, _ = client
    r = j(c.get("/api/recommendations"))
    assert r["blocked"] is True
    assert r["long"] == [] and r["short"] == []


def test_synthetic_data_never_produces_recommendations(client):
    c, app = client
    seed(app, synthetic=True)
    s = j(c.get("/api/status"))
    assert s["has_data"] is False
    assert s["synthetic_rows"] > 0
    assert "Practice data" in json.dumps(s["gate"])
    r = j(c.get("/api/recommendations"))
    assert r["blocked"] is True


def test_stale_data_blocks_recommendations(client):
    """Data that stops months ago must not generate trade ideas."""
    c, app = client
    seed(app)
    r = j(c.get("/api/recommendations"))
    # the seeded history ends in 2025 while 'today' is later, so the
    # staleness check must bite
    assert r["blocked"] is True
    assert "DATA QUALITY" in r["reason"] or "history" in r["reason"].lower()


def test_recommendations_include_evidence_when_allowed(client, monkeypatch):
    c, app = client
    seed(app)
    import app.gui.server as srv

    class AlwaysOK:
        ok = True
        errors: list = []
        warnings: list = []

    monkeypatch.setattr(srv, "validate_daily_v2", lambda *a, **k: AlwaysOK())
    r = j(c.get("/api/recommendations"))
    assert r["blocked"] is False
    for side in ("long", "short"):
        for cand in r[side]:
            p = cand["probability"]
            assert "display" in p and "evidence" in p
            # with no calibration built, it must refuse to invent a number
            assert p["available"] is False
            assert p["display"] == "Insufficient data"
            assert cand["quantity"] > 0
            assert cand["stop"] != cand["entry"]
            assert cand["rr"] > 0
    assert "portfolio" in r


# --------------------------------------------------------- other pages ----
def test_heatmap_without_index_data(client):
    c, app = client
    seed(app, with_index=False)
    h = j(c.get("/api/heatmap"))
    assert h["sectors"] == []
    assert "No index data" in h["message"]


def test_heatmap_with_index_data(client):
    c, app = client
    seed(app)
    h = j(c.get("/api/heatmap"))
    names = [x["index_name"] for x in h["sectors"] + h["broad"]]
    assert "NIFTY 50" in names
    for row in h["sectors"] + h["broad"]:
        assert row["band"] in ("strong_bull", "bull", "neutral", "bear",
                               "strong_bear", "unknown")


def test_chart_endpoint(client):
    c, app = client
    seed(app)
    d = j(c.get("/api/chart/T01?range=6M"))
    assert d["symbol"] == "T01"
    assert len(d["dates"]) == len(d["close"]) == len(d["volume"])
    assert len(d["rsi"]) == len(d["close"])
    assert d["entry"] and d["stop"] and d["target"]
    assert d["stop"] < d["entry"] < d["target"]
    assert isinstance(d["support"], list)


def test_chart_unknown_symbol_404(client):
    c, app = client
    seed(app)
    assert c.get("/api/chart/NOPE").status_code == 404


def test_sector_drilldown(client):
    c, app = client
    seed(app)
    d = j(c.get("/api/sector/NIFTY%20BANK/stocks"))
    assert "stocks" in d


# ----------------------------------------------------------- settings -----
def test_settings_round_trip(client):
    c, _ = client
    d = j(c.get("/api/settings"))
    assert d["settings"]["capital"] == 1_000_000.0
    r = j(c.post("/api/settings", json={"capital": 250000,
                                        "risk_per_trade_pct": 0.5}))
    assert r["ok"] is True
    assert j(c.get("/api/settings"))["settings"]["capital"] == 250000


def test_settings_persist_across_app_restart(tmp_path):
    root = build_root(tmp_path)
    a1 = create_app(str(root))
    a1.test_client().post("/api/settings", json={"capital": 777777})
    a2 = create_app(str(root))
    s = json.loads(a2.test_client().get("/api/settings").data)
    assert s["settings"]["capital"] == 777777


def test_insane_risk_is_capped(client):
    c, _ = client
    r = j(c.post("/api/settings", json={"risk_per_trade_pct": 95}))
    assert r["settings"]["risk_per_trade_pct"] == 10.0
    assert any("dangerous" in w for w in r["warnings"])


def test_negative_capital_rejected(client):
    c, _ = client
    r = c.post("/api/settings", json={"capital": -5})
    assert r.status_code == 400


def test_reset_to_safe_defaults(client):
    c, _ = client
    c.post("/api/settings", json={"capital": 12345})
    c.post("/api/settings/reset")
    assert j(c.get("/api/settings"))["settings"]["capital"] == 1_000_000.0


# ----------------------------------------------------------- telegram -----
def test_telegram_token_never_returned(client, tmp_path):
    c, app = client
    c.post("/api/telegram/save", json={"token": "123:SECRETTOKEN",
                                       "chat_id": "999888"})
    body = c.get("/api/telegram/status").data.decode()
    assert "SECRETTOKEN" not in body
    assert j(c.get("/api/telegram/status"))["configured"] is True
    env = app.config["SETTINGS"].root / "config" / ".env"
    assert "SECRETTOKEN" in env.read_text()


# ------------------------------------------------------------ backups -----
def test_backup_and_list(client):
    c, app = client
    seed(app)
    r = j(c.post("/api/run/backup"))
    assert r["status"] in ("running", "done")
    for _ in range(80):
        st = j(c.get("/api/job"))
        if st.get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    assert st["status"] == "done", st
    b = j(c.get("/api/backups"))
    assert len(b["backups"]) >= 1
    assert b["backups"][0]["ok"] is True
    assert b["backups"][0]["checksum_short"]


def test_restore_rejects_missing_file(client):
    c, _ = client
    assert c.post("/api/backups/restore", json={"file": "nope.sqlite"}
                  ).status_code == 404


# --------------------------------------------------------------- jobs -----
def test_only_one_job_at_a_time():
    m = JobManager()
    m.start("slow", lambda job: time.sleep(0.6))
    with pytest.raises(RuntimeError):
        m.start("other", lambda job: None)


def test_job_records_error_in_plain_language():
    m = JobManager()
    def boom(job):
        raise ConnectionError("max retries exceeded")
    m.start("bad", boom)
    for _ in range(60):
        jb = m.current()
        if jb.status != "running":
            break
        time.sleep(0.05)
    assert jb.status == "error"
    assert "internet" in jb.message.lower()


def test_job_can_be_cancelled():
    m = JobManager()
    from app.gui.jobs import should_stop
    def loop(job):
        stop = should_stop(job)
        for _ in range(200):
            if stop():
                return "stopped"
            time.sleep(0.01)
        return "ran to completion"
    jb = m.start("loop", loop)
    time.sleep(0.1)
    assert m.cancel(jb.id) is True
    time.sleep(0.2)
    assert jb.status == "cancelled"


def test_progress_percentage():
    from app.gui.jobs import Job, progress_adapter
    jb = Job(id="x", name="t")
    cb = progress_adapter(jb)
    cb("half way", 5, 10)
    assert jb.percent == 50
    assert jb.message == "half way"
    assert "half way" in jb.steps


@pytest.mark.parametrize("exc,expect", [
    (ConnectionError("refused"), "internet"),
    (RuntimeError("HTTP 403 Forbidden"), "refused the request"),
    (RuntimeError("429 rate limit"), "slow down"),
    (PermissionError("denied"), "write-protected"),
])
def test_friendly_errors(exc, expect):
    assert expect in friendly_error(exc).lower() or \
        expect in friendly_error(exc)


# ---------------------------------------------------------------- logs ----
def test_log_endpoints(client):
    c, app = client
    seed(app)
    for kind in ("app", "quality", "gaps", "corporate"):
        r = c.get(f"/api/logs?kind={kind}")
        assert r.status_code == 200


def test_sources_page_without_probe(client):
    c, _ = client
    d = j(c.get("/api/sources"))
    assert d["sources"] == []


def test_unknown_action_rejected(client):
    c, _ = client
    assert c.post("/api/run/nonsense").status_code == 400


# ------------------------------------------- data sources page regressions --
def test_source_summary_maps_probe_status_names(client, tmp_path):
    """The page showed '—' for every counter.

    probe_sources.py writes WORKING / FAILED / BLOCKED / RATE_LIMITED /
    SKIPPED / NOT_PUBLISHED, but the API was reading ok / fail / blocked,
    so nothing ever matched.
    """
    c, app = client
    reports = app.config["SETTINGS"].reports_dir
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "source_probe_20260101_000000.json").write_text(json.dumps({
        "generated_at_utc": dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="seconds"),
        "summary": {"WORKING": 9, "FAILED": 3, "BLOCKED": 1,
                    "RATE_LIMITED": 1, "SKIPPED": 2},
        "results": [{"source": "nse:bhavcopy_udiff_cm", "status": "WORKING",
                     "latency_ms": 120, "http_status": 200}],
    }))
    d = j(c.get("/api/sources"))
    assert d["summary"]["ok"] == 9
    assert d["summary"]["fail"] == 3
    assert d["summary"]["blocked"] == 2      # BLOCKED + RATE_LIMITED
    assert d["summary"]["skipped"] == 2
    assert d["stale"] is False
    assert len(d["sources"]) == 1


def test_old_source_probe_is_marked_stale(client):
    """A day-old FAILED verdict must not look like today's truth."""
    c, app = client
    reports = app.config["SETTINGS"].reports_dir
    reports.mkdir(parents=True, exist_ok=True)
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=30)
    (reports / "source_probe_20250101_000000.json").write_text(json.dumps({
        "generated_at_utc": old.isoformat(timespec="seconds"),
        "summary": {"FAILED": 14}, "results": [],
    }))
    d = j(c.get("/api/sources"))
    assert d["stale"] is True
    assert 29 < d["age_hours"] < 31


def test_request_log_is_quietened(client):
    import logging as _l
    assert _l.getLogger("werkzeug").level >= _l.WARNING, \
        "polling /api/job every second must not flood the log file"
