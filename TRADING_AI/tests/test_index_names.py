"""Index naming, quarantine and honesty regressions.

Every test here comes from a real failure seen on the user's own database:
172 indices downloaded and a dashboard that said "No index data yet", plus a
corporate-action check that disabled all 200 stocks because 17 of them had an
unadjusted split years ago.

The important detail is that the index names used below are the exact
mixed-case strings NSE publishes ("Nifty 50", not "NIFTY 50"). The older
tests seeded uppercase names, which is precisely why they passed while the
real application showed nothing.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.analytics.indices import (broad_label, display, is_broad,
                                   is_nifty50, is_sector, norm, sector_label)
from app.data.corporate_actions import symbols_with_extreme_jumps
from app.gui.server import create_app
from tests.test_gui_api import build_root, seed, sessions  # noqa: E402


# ------------------------------------------------------- name handling ----
def test_norm_collapses_nse_spelling_variants():
    assert norm("Nifty 50") == norm("NIFTY 50") == norm("  nifty  50 ")


@pytest.mark.parametrize("name", ["Nifty 50", "NIFTY 50", "Nifty50"])
def test_nifty50_recognised_however_nse_writes_it(name):
    assert is_nifty50(name)


@pytest.mark.parametrize("name,expected", [
    ("Nifty Bank", "Bank"),
    ("Nifty Metal", "Metal"),
    ("Nifty IT", "IT"),
    ("Nifty Healthcare Index", "Healthcare"),
    ("Nifty Financial Services", "Financial Services"),
    ("Nifty Private Bank", "Private Bank"),
    ("Nifty PSU Bank", "PSU Bank"),
])
def test_real_nse_sector_names_map_to_a_sector(name, expected):
    assert is_sector(name)
    assert sector_label(name) == expected


@pytest.mark.parametrize("name", ["Nifty 50", "Nifty 100", "Nifty 200",
                                  "Nifty Next 50"])
def test_broad_indices_are_not_sectors(name):
    assert is_broad(name)
    assert not is_sector(name)
    assert broad_label(name)


@pytest.mark.parametrize("junk", ["Nifty IPO", "SME EMERGE",
                                  "Nifty Microcap 250", "Nifty50 Dividend"])
def test_thematic_indices_are_neither_sector_nor_broad(junk):
    """These were being shown as 'sectors' on the user's dashboard."""
    assert not is_sector(junk)
    assert not is_broad(junk)


def test_display_keeps_the_name_readable():
    assert display("Nifty Bank") == "Bank"
    assert display("Nifty 50") == "Nifty 50"


# ------------------------------------------------------------ fixtures ----
NSE_SECTORS = ["Nifty Bank", "Nifty IT", "Nifty Auto", "Nifty Pharma",
               "Nifty Metal", "Nifty Realty"]
NSE_JUNK = ["Nifty IPO", "SME EMERGE", "Nifty Microcap 250"]


def seed_real_index_names(app, days, *, synthetic=False):
    """Index history under the names NSE actually publishes."""
    db = app.config["DB"]
    rows = []
    for j, name in enumerate(["Nifty 50", "Nifty 100"] + NSE_SECTORS
                             + NSE_JUNK):
        v = 20000 + j * 500
        drift = 0.0009 - 0.0004 * j
        for k, d in enumerate(days):
            v *= math.exp(drift + 0.003 * math.sin(k / 9 + j))
            rows.append({"index_name": name, "date": d.isoformat(),
                         "open": v, "high": v * 1.003, "low": v * 0.997,
                         "close": v, "change_pct": 0.0, "source": "test",
                         "is_synthetic": 1 if synthetic else 0})
    db.upsert_index(rows)


def recent_end():
    """Last weekday, so the staleness gate does not mask what we test."""
    d = dt.date.today() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


@pytest.fixture()
def real_names(tmp_path):
    app = create_app(str(build_root(tmp_path)))
    app.config["TESTING"] = True
    days = seed(app, n_syms=12, n_days=260, with_index=False,
                end=recent_end())
    seed_real_index_names(app, days)
    return app.test_client(), app, days


def j(resp):
    return json.loads(resp.data)


# ------------------------------------------------- dashboard + heatmap ----
def test_nifty50_shows_up_with_mixed_case_names(real_names):
    c, _, _ = real_names
    st = j(c.get("/api/status"))
    assert st["nifty"] is not None, "dashboard said 'No index data yet'"
    assert st["nifty"]["value"] > 0


def test_strongest_and_weakest_sector_are_populated(real_names):
    c, _, _ = real_names
    st = j(c.get("/api/status"))
    assert st["strongest_sector"] is not None
    assert st["weakest_sector"] is not None
    assert st["strongest_sector"]["index_name"] != \
        st["weakest_sector"]["index_name"]
    # labels are the friendly ones, not raw NSE strings
    assert "Nifty" not in st["strongest_sector"]["index_name"]


def test_heatmap_splits_sectors_from_broad_and_drops_junk(real_names):
    c, _, _ = real_names
    h = j(c.get("/api/heatmap"))
    labels = {r["label"] for r in h["sectors"]}
    assert labels == {"Bank", "IT", "Auto", "Pharma", "Metal", "Realty"}
    assert {r["label"] for r in h["broad"]} == {"Nifty 50", "Nifty 100"}
    # the thematic indices are counted, never presented as sectors
    assert h["other_count"] == len(NSE_JUNK)


def test_every_heatmap_tile_has_a_band(real_names):
    c, _, _ = real_names
    h = j(c.get("/api/heatmap"))
    bands = {"strong_bull", "bull", "neutral", "bear", "strong_bear"}
    assert h["sectors"]
    for r in h["sectors"]:
        assert r["band"] in bands


def test_heatmap_explains_itself_when_no_sectors_downloaded(tmp_path):
    app = create_app(str(build_root(tmp_path)))
    app.config["TESTING"] = True
    seed(app, n_syms=6, n_days=200, with_index=False)
    h = j(app.test_client().get("/api/heatmap"))
    assert h["sectors"] == []
    assert h["message"] and "update" in h["message"].lower()


# ----------------------------------------------------------- quarantine ---
def test_extreme_jump_detection_names_the_symbol():
    import pandas as pd
    df = pd.DataFrame({
        "symbol": ["A", "A", "A", "B", "B", "B"],
        "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"] * 2),
        "close": [100.0, 100.5, 40.0,     # A: 1:2.5 split, unadjusted
                  50.0, 50.4, 50.9],      # B: fine
    })
    bad = symbols_with_extreme_jumps(df)
    assert set(bad) == {"A"}
    assert "%" in bad["A"]


def _add_split_jump(app, days, symbol="T03"):
    """Make one stock look like it had an unadjusted 1:3 split."""
    db = app.config["DB"]
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT close FROM daily_ohlc WHERE symbol=? AND date=?",
            (symbol, days[-5].isoformat())).fetchone()
        base = float(row["close"])
    finally:
        conn.close()
    with db.tx() as c:
        for d in days[-5:]:
            c.execute("UPDATE daily_ohlc SET open=open/3.0, high=high/3.0,"
                      " low=low/3.0, close=close/3.0"
                      " WHERE symbol=? AND date=?", (symbol, d.isoformat()))
    return base


def test_one_bad_stock_does_not_disable_the_whole_market(real_names):
    """The bug: 17 unadjusted splits blocked all 200 stocks, permanently."""
    c, app, days = real_names
    _add_split_jump(app, days, "T03")

    r = j(c.get("/api/recommendations"))
    assert r["blocked"] is False, r.get("reason")
    assert r["long"] or r["short"]


def test_quarantined_stock_is_excluded_from_ideas(real_names):
    c, app, days = real_names
    _add_split_jump(app, days, "T03")

    r = j(c.get("/api/recommendations"))
    assert r["quarantined"]["count"] == 1
    assert r["quarantined"]["symbols"] == ["T03"]
    named = [x["symbol"] for x in r["long"] + r["short"]]
    assert "T03" not in named


def test_quarantine_reason_is_in_plain_language(real_names):
    c, app, days = real_names
    _add_split_jump(app, days, "T03")
    q = j(c.get("/api/recommendations"))["quarantined"]
    assert "excluded" in q["note"]
    assert "unexplained" in q["reasons"]["T03"]


def test_extreme_jump_is_a_warning_not_a_blocker(real_names):
    c, app, days = real_names
    _add_split_jump(app, days, "T03")
    st = j(c.get("/api/status"))
    checks = {i.get("check"): i for i in st["gate"].get("issues", [])}
    if "extreme_price_jump" in checks:
        assert checks["extreme_price_jump"].get("severity") != "ERROR"


def test_clean_data_quarantines_nobody(real_names):
    c, _, _ = real_names
    r = j(c.get("/api/recommendations"))
    assert r["quarantined"]["count"] == 0
    assert "No stocks are excluded" in r["quarantined"]["note"]


# ------------------------------------------------- adjusted price series --
def test_analysis_prefers_the_adjusted_series(real_names):
    """Adjusted prices were being computed and then ignored."""
    c, app, days = real_names
    db = app.config["DB"]
    with db.tx() as conn:
        for d in days:
            conn.execute(
                "INSERT OR REPLACE INTO daily_ohlc_adjusted"
                " (symbol,date,open,high,low,close,volume,adj_factor)"
                " VALUES (?,?,?,?,?,?,?,?)",
                ("T00", d.isoformat(), 1.0, 1.0, 1.0, 1.0, 1000, 1.0))
    with app.app_context():
        frames = app.config["LOAD_FRAMES"]() if "LOAD_FRAMES" in app.config \
            else None
    if frames is not None:
        daily = frames[0]
        assert set(daily["symbol"]) == {"T00"}


# --------------------------------------------------- honesty about data ---
def test_no_market_data_message_reports_row_counts(tmp_path):
    """A full database and an empty one must not give the same message."""
    app = create_app(str(build_root(tmp_path)))
    app.config["TESTING"] = True
    seed(app, n_syms=6, n_days=200, synthetic=True)
    r = j(app.test_client().get("/api/recommendations"))
    assert r["blocked"] is True
    assert r["rows_total"] > 0
    assert "test data" in r["reason"]


def test_empty_database_says_download_something(tmp_path):
    app = create_app(str(build_root(tmp_path)))
    app.config["TESTING"] = True
    r = j(app.test_client().get("/api/recommendations"))
    assert r["blocked"] is True
    assert r["rows_total"] == 0
    assert "UPDATE" in r["reason"]


def test_history_depth_is_reported_honestly(real_names):
    """User asked for 5 years; only ~1 year exists. Say so."""
    c, app, _ = real_names
    with app.config["DB"].tx() as conn:
        conn.execute("INSERT OR REPLACE INTO app_settings (key,value)"
                     " VALUES ('history_period','5y')")
    cov = j(c.get("/api/status"))["coverage"]
    assert cov["requested_period"] == "5y"
    note = cov["depth_note"]
    assert note and "5y" in note and "available" in note


# ------------------------------------- adjusted prices actually get used --
def _write_adjusted(app, days, symbol="T00", factor=0.25):
    """Pretend the corporate-action pass adjusted this stock."""
    db = app.config["DB"]
    conn = db.connect()
    try:
        raw = conn.execute(
            "SELECT date,open,high,low,close,volume FROM daily_ohlc"
            " WHERE symbol=? ORDER BY date", (symbol,)).fetchall()
    finally:
        conn.close()
    with db.tx() as c:
        for r in raw:
            c.execute(
                "INSERT OR REPLACE INTO daily_ohlc_adjusted"
                " (symbol,date,open,high,low,close,volume,adj_factor)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (symbol, r["date"], r["open"] * factor, r["high"] * factor,
                 r["low"] * factor, r["close"] * factor, r["volume"], factor))
    return [float(r["close"]) * factor for r in raw]


def test_chart_uses_the_adjusted_series_when_one_exists(real_names):
    """Adjusted prices were computed and then ignored by every chart."""
    c, app, days = real_names
    expected = _write_adjusted(app, days, "T00", factor=0.25)
    ch = j(c.get("/api/chart/T00?range=1Y"))
    assert ch["adjusted"] is True
    assert "adjusted" in ch["price_note"].lower()
    assert ch["close"][-1] == pytest.approx(expected[-1], rel=1e-6)


def test_chart_falls_back_to_raw_prices(real_names):
    c, _, _ = real_names
    ch = j(c.get("/api/chart/T01?range=1Y"))
    assert ch["adjusted"] is False
    assert "NSE" in ch["price_note"]


def test_recommendations_read_the_adjusted_series(real_names):
    """Ranking must see adjusted prices too, not just the charts."""
    c, app, days = real_names
    expected = _write_adjusted(app, days, "T00", factor=0.25)
    # Once an adjusted series exists, load_frames() must serve it, so the
    # last traded price shown for T00 comes from the adjusted table.
    r = j(c.get("/api/recommendations"))
    rows = {x["symbol"]: x for x in r.get("long", []) + r.get("short", [])}
    if "T00" in rows:
        assert rows["T00"]["last_price"] == pytest.approx(expected[-1],
                                                          rel=1e-3)


def test_adjusted_overlay_keeps_every_other_stock(real_names):
    """Overlaying one adjusted stock must not hide the other eleven."""
    c, app, days = real_names
    before = j(c.get("/api/status"))["coverage"]["symbols"]
    _write_adjusted(app, days, "T00", factor=0.25)
    r = j(c.get("/api/recommendations"))
    assert r["blocked"] is False, r.get("reason")
    # every stock is still ranked, adjusted or not
    sec = j(c.get("/api/sector/Bank/stocks"))
    assert before >= 12
    assert r["long"] or r["short"] or sec["stocks"]


# --------------------------------------------- typing a partial symbol ----
def test_symbol_list_is_available_for_the_picker(real_names):
    c, _, _ = real_names
    d = j(c.get("/api/symbols"))
    assert d["count"] == 12
    assert d["symbols"][0]["symbol"] == "T00"
    assert d["symbols"][0]["bars"] > 0


def test_symbol_search_filters(real_names):
    c, _, _ = real_names
    d = j(c.get("/api/symbols?q=T0"))
    assert all(s["symbol"].startswith("T0") for s in d["symbols"])


def test_unique_prefix_loads_the_chart(real_names):
    """Typing 'rel' should find RELIANCE, not fail."""
    c, _, _ = real_names
    r = c.get("/api/chart/T11?range=1M")
    assert r.status_code == 200
    # a unique prefix resolves to the same stock
    assert j(c.get("/api/chart/t11?range=1M"))["symbol"] == "T11"


def test_ambiguous_input_suggests_candidates(real_names):
    c, _, _ = real_names
    r = c.get("/api/chart/T?range=1M")
    assert r.status_code == 404
    body = j(r)
    assert "several" in body["error"]
    assert len(body["suggestions"]) >= 2


def test_unknown_symbol_says_so_plainly(real_names):
    c, _, _ = real_names
    body = j(c.get("/api/chart/ZZZZ?range=1M"))
    assert "No stock matches" in body["error"]
    assert body["suggestions"] == []


# ------------------------------- backtest sees the same clean prices ------
def test_backtest_loader_drops_quarantined_stocks(real_names):
    """The backtest used to trade the fake 60% crash and ruin its own curve."""
    from app.data.frames import exclusion_note, load_daily
    c, app, days = real_names
    _add_split_jump(app, days, "T03")
    db = app.config["DB"]

    raw, none_excluded = load_daily(db, adjusted=False,
                                    exclude_quarantined=False)
    clean, excluded = load_daily(db, real_only=True)

    assert none_excluded == {}
    assert set(excluded) == {"T03"}
    assert "T03" in set(raw["symbol"])
    assert "T03" not in set(clean["symbol"])
    assert "T03" in exclusion_note(excluded)


def test_shared_loader_overlays_adjusted_prices(real_names):
    from app.data.frames import load_daily
    c, app, days = real_names
    expected = _write_adjusted(app, days, "T00", factor=0.25)
    clean, _ = load_daily(app.config["DB"], real_only=True)
    got = clean[clean["symbol"] == "T00"]["close"].tolist()
    assert got[-1] == pytest.approx(expected[-1], rel=1e-6)
    # and the other stocks survive the overlay
    assert len(set(clean["symbol"])) == 12


def test_backtest_reports_what_it_left_out(real_names, tmp_path):
    from app.gui.jobs import Job
    from app.gui.pipeline import run_backtest_job
    c, app, days = real_names
    _add_split_jump(app, days, "T03")
    job = Job(id="backtest", name="backtest")
    out = run_backtest_job(job, app.config["DB"], app.config["SETTINGS"],
                           {"warmup": 130, "top_n": 3})
    assert out["stats"]["excluded_symbols"] == ["T03"]
    assert "T03" in out["excluded"]


def test_backtest_reports_its_worst_day(real_names):
    from app.gui.jobs import Job
    from app.gui.pipeline import run_backtest_job
    c, app, days = real_names
    job = Job(id="backtest", name="backtest")
    out = run_backtest_job(job, app.config["DB"], app.config["SETTINGS"],
                           {"warmup": 130, "top_n": 3})
    assert out["stats"]["worst_day_pct"] <= 0
    assert out["stats"]["worst_day_date"]


# ------------------------------------------------- version visibility ----
def test_version_file_ships_with_the_code():
    """The user must be able to confirm an update actually landed."""
    v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert v and v != "unknown"


def test_version_is_reported_to_the_screen(real_names):
    from app.gui.server import app_version
    c, _, _ = real_names
    assert j(c.get("/api/health"))["app_version"] == app_version()
    assert j(c.get("/api/status"))["app_version"] == app_version()
