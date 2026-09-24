"""Out-of-sample settings testing.

The risk this guards against is subtle and expensive: run a sweep, pick the
best row, trade it, lose money. A sweep always has a best row. These tests
check that the module reports *consistency across two halves* rather than a
winner, and that it is willing to conclude "nothing here works".
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.backtest.engine import CostModel
from app.backtest.robustness import (DEFAULT_GRID, Setting, conclusion,
                                     cost_hurdle, sweep, verdict)
from tests.test_gui_api import build_root, seed  # noqa: E402
from tests.test_index_names import j, recent_end  # noqa: E402


# ------------------------------------------------------------- verdicts ---
@pytest.mark.parametrize("a,b,expect", [
    (10.0, 8.0, "Positive in both halves"),
    (20.0, -5.0, "Worked then stopped working - likely fitted to the past"),
    (-4.0, -6.0, "Lost money in both halves"),
    (-3.0, 9.0, "Only worked in the later half - not evidence of an edge"),
    (30.0, 2.0, "Much weaker in the second half - treat with caution"),
])
def test_verdict_wording(a, b, expect):
    assert verdict({"return_pct": a}, {"return_pct": b}) == expect


def test_verdict_refuses_to_guess_without_numbers():
    assert verdict({"return_pct": float("nan")},
                   {"return_pct": 5.0}) == "Not enough data to judge"


# ------------------------------------------------------------ conclusion --
def _table(rows):
    return pd.DataFrame([{
        "label": r[0], "rebalance_days": r[1], "top_n": 5, "trades": 100,
        "cost_drag_pct": 10.0, "max_dd_pct": -20.0,
        "first_half_return_pct": r[2], "second_half_return_pct": r[3],
        "verdict": verdict({"return_pct": r[2]}, {"return_pct": r[3]}),
    } for r in rows])


def test_conclusion_says_so_when_nothing_survives():
    """The honest answer for a strategy that loses after costs."""
    t = _table([("A", 5, 18.0, -9.0), ("B", 10, 4.0, -2.0),
                ("C", 21, -3.0, -1.0)])
    c = conclusion(t)
    assert c["ok"] is False
    assert "No setting made money in both halves" in c["headline"]
    # it must name the trap: the best-looking one did badly afterwards
    assert "+18.0%" in c["detail"] and "-9.0%" in c["detail"]
    assert "should" in c["detail"] and "not be traded" in c["detail"]


def test_conclusion_stays_measured_when_something_survives():
    t = _table([("A", 5, 12.0, 9.0), ("B", 10, -2.0, 3.0)])
    c = conclusion(t)
    assert c["ok"] is True
    assert c["recommended"]["rebalance_days"] == 5
    # even a survivor is not sold as proof
    assert "weak evidence, not proof" in c["detail"]


def test_conclusion_handles_no_data():
    c = conclusion(pd.DataFrame())
    assert c["ok"] is False
    assert "Not enough history" in c["headline"]


# ----------------------------------------------------------- cost hurdle --
def test_cost_hurdle_matches_the_engines_own_cost_model():
    """The hurdle must not drift from what the backtest actually charges."""
    c = CostModel()
    n = 200_000.0
    expected = (c.buy_cost(n) + c.sell_cost(n)) / n * 100
    h = cost_hurdle(costs=c, rebalance_days=5)
    # the stored figure is rounded for display; it must still match
    assert h["round_trip_cost_pct"] == pytest.approx(expected, abs=5e-5)


def test_trading_more_often_costs_proportionally_more():
    fast = cost_hurdle(rebalance_days=5)["annual_cost_pct"]
    slow = cost_hurdle(rebalance_days=21)["annual_cost_pct"]
    assert fast > slow
    assert fast / slow == pytest.approx(21 / 5, rel=0.02)


def test_cost_hurdle_is_material_at_weekly_rebalancing():
    """Roughly 17% a year at 5-day holds - the reason the strategy lost."""
    h = cost_hurdle(rebalance_days=5)
    assert 10 < h["annual_cost_pct"] < 30
    assert "%" in h["note"]


# ----------------------------------------------------------------- sweep --
def _fixture(tmp_path, n_days=420):
    app = create_app(str(build_root(tmp_path)))
    app.config["TESTING"] = True
    seed(app, n_syms=10, n_days=n_days, with_index=False, end=recent_end())
    conn = app.config["DB"].connect()
    try:
        daily = pd.read_sql_query(
            "SELECT symbol,date,open,high,low,close,volume FROM daily_ohlc"
            " ORDER BY symbol,date", conn)
    finally:
        conn.close()
    return app, daily


from app.gui.server import create_app  # noqa: E402  (after ROOT on path)


def test_sweep_scores_both_halves_of_every_setting(tmp_path):
    _, daily = _fixture(tmp_path)
    grid = [Setting(21, 3), Setting(63, 3)]
    t = sweep(daily, warmup=130, grid=grid)
    assert len(t) == len(grid)
    for col in ("first_half_return_pct", "second_half_return_pct",
                "trades", "cost_drag_pct", "verdict", "split_date"):
        assert col in t.columns
    assert t["verdict"].notna().all()


def test_sweep_refuses_when_history_is_too_short(tmp_path):
    _, daily = _fixture(tmp_path, n_days=150)
    assert sweep(daily, warmup=130).empty


def test_slower_rebalancing_trades_less_and_costs_less(tmp_path):
    """The mechanism behind the cost finding, checked end to end."""
    _, daily = _fixture(tmp_path)
    t = sweep(daily, warmup=130, grid=[Setting(5, 3), Setting(63, 3)])
    fast = t[t["rebalance_days"] == 5].iloc[0]
    slow = t[t["rebalance_days"] == 63].iloc[0]
    assert fast["trades"] > slow["trades"]
    assert fast["cost_drag_pct"] > slow["cost_drag_pct"]


def test_default_grid_is_small_on_purpose():
    """A wide grid is a licence to overfit."""
    assert len(DEFAULT_GRID) <= 6


# ------------------------------------------------------------ in the app --
def test_robustness_endpoint_before_any_run(tmp_path):
    app = create_app(str(build_root(tmp_path)))
    app.config["TESTING"] = True
    d = j(app.test_client().get("/api/robustness"))
    assert d["available"] is False
    assert "TEST SETTINGS" in d["message"]


def test_robustness_job_stores_and_serves_its_result(tmp_path):
    from app.gui.jobs import Job
    from app.gui.pipeline import run_robustness_job

    app, _ = _fixture(tmp_path)
    job = Job(id="rob", name="rob")
    out = run_robustness_job(job, app.config["DB"], app.config["SETTINGS"],
                             {"warmup": 130})
    assert out["available"] is True
    assert out["rows"] and out["conclusion"]
    assert out["cost_hurdles"]

    served = j(app.test_client().get("/api/robustness"))
    assert served["available"] is True
    assert len(served["rows"]) == len(out["rows"])
    assert served["conclusion"]["headline"] == out["conclusion"]["headline"]
