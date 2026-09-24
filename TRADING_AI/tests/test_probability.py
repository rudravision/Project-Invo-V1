"""Probability engine and position sizing.

These tests exist to enforce two promises made to the user:
  1. a probability is only ever shown when enough out-of-sample evidence
     stands behind it;
  2. position size comes from stop distance, not from splitting capital
     evenly.
"""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.analytics.probability import (MIN_OBSERVATIONS, Calibrator,
                                       Probability, build_calibration,
                                       persist_calibration)
from app.analytics.recommend import (RiskSettings, compute_levels,
                                     portfolio_summary, size_position)
from app.db.database import Database
from app.db.migrations import migrate


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "t.sqlite")
    migrate(d, tmp_path / "backups")
    return d


def synth_panel(n_syms=25, n_days=420, seed=3):
    rng = np.random.default_rng(seed)
    start = dt.date(2023, 1, 2)
    days, d = [], start
    while len(days) < n_days:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    rows = []
    for i in range(n_syms):
        p = 100 + i * 10
        drift = rng.normal(0.0003, 0.0004)
        for day in days:
            p *= math.exp(rng.normal(drift, 0.015))
            rows.append({"symbol": f"S{i:02d}", "date": day.isoformat(),
                         "open": p * 0.998, "high": p * 1.01, "low": p * 0.99,
                         "close": p, "volume": 500_000, "is_synthetic": 0})
    return pd.DataFrame(rows)


# ------------------------------------------------------------- refusals ---
def test_no_calibration_means_insufficient_data(db):
    c = Calibrator(db)
    assert not c.ready
    p = c.probability(1.5)
    assert p.available is False
    assert p.display == "Insufficient data"
    assert "no calibration" in p.note.lower()


def test_thin_bucket_refuses_to_show_a_number(db):
    with db.tx() as c:
        c.execute(
            "INSERT INTO probability_calibration (model_version,horizon_days,"
            "bucket,score_lo,score_hi,n_observations,n_positive,hit_rate,"
            "mean_return,fold) VALUES ('rank_v1',1,0,0.0,1.0,50,30,0.6,"
            "0.004,'walkforward')")
    p = Calibrator(db).probability(0.5)
    assert p.available is False
    assert p.n_observations == 50
    assert p.display == "Insufficient data"
    assert "50" in p.evidence and str(MIN_OBSERVATIONS) in p.evidence


def test_rich_bucket_shows_the_observed_frequency(db):
    with db.tx() as c:
        c.execute(
            "INSERT INTO probability_calibration (model_version,horizon_days,"
            "bucket,score_lo,score_hi,n_observations,n_positive,hit_rate,"
            "mean_return,fold) VALUES ('rank_v1',1,0,0.0,1.0,900,522,0.58,"
            "0.004,'walkforward')")
    p = Calibrator(db).probability(0.5)
    assert p.available is True
    assert p.value == pytest.approx(0.58)
    assert p.display == "58%"
    assert "900" in p.evidence


def test_score_outside_calibrated_range_refuses(db):
    with db.tx() as c:
        c.execute(
            "INSERT INTO probability_calibration (model_version,horizon_days,"
            "bucket,score_lo,score_hi,n_observations,n_positive,hit_rate,"
            "mean_return,fold) VALUES ('rank_v1',1,0,0.0,1.0,900,522,0.58,"
            "0.004,'walkforward')")
    p = Calibrator(db).probability(9.9)
    assert p.available is False
    assert "outside" in p.note


def test_short_probability_is_the_complement_not_a_flipped_score(db):
    with db.tx() as c:
        c.executemany(
            "INSERT INTO probability_calibration (model_version,horizon_days,"
            "bucket,score_lo,score_hi,n_observations,n_positive,hit_rate,"
            "mean_return,fold) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [("rank_v1", 1, 0, -2.0, 0.0, 800, 344, 0.43, -0.003, "walkforward"),
             ("rank_v1", 1, 1, 0.0, 2.0, 800, 464, 0.58, 0.004, "walkforward")])
    c = Calibrator(db)
    long_p = c.probability_for(1.0, "LONG")
    short_p = c.probability_for(1.0, "SHORT")
    assert long_p.value == pytest.approx(0.58)
    # same bucket, complementary outcome -- NOT the -1.0 bucket's 0.43
    assert short_p.value == pytest.approx(0.42)
    assert short_p.n_observations == 800


# ---------------------------------------------------------- walk-forward ---
def test_calibration_is_out_of_sample(db):
    """The scoring function must only ever receive past data."""
    panel = synth_panel()
    seen_future = []

    def score_fn(hist, as_of):
        if hist["date"].max() > pd.Timestamp(as_of):
            seen_future.append(as_of)
        n = hist["symbol"].nunique()
        return pd.DataFrame({"symbol": sorted(hist["symbol"].unique()),
                             "score": np.linspace(-1, 1, n)})

    cal = build_calibration(panel, score_fn, n_folds=3, min_train=250)
    assert not seen_future, "score function was given future data"
    assert not cal.empty
    assert (cal["n_observations"] > 0).all()
    assert cal["hit_rate"].between(0, 1).all()
    assert (cal["n_positive"] <= cal["n_observations"]).all()


def test_calibration_round_trip(db):
    panel = synth_panel()

    def score_fn(hist, as_of):
        n = hist["symbol"].nunique()
        return pd.DataFrame({"symbol": sorted(hist["symbol"].unique()),
                             "score": np.linspace(-1, 1, n)})

    cal = build_calibration(panel, score_fn, n_folds=3, min_train=250)
    n = persist_calibration(db, cal)
    assert n == len(cal)
    c = Calibrator(db)
    assert c.ready
    assert c.total_observations == int(cal["n_observations"].sum())
    s = c.summary()
    assert s["buckets"] == len(cal)
    assert s["usable_buckets"] <= s["buckets"]


def test_short_history_calibrates_to_nothing():
    small = synth_panel(n_syms=5, n_days=60)
    assert build_calibration(small, lambda h, a: None).empty


# -------------------------------------------------------- position sizing --
def test_size_scales_inversely_with_stop_distance():
    rs = RiskSettings(capital=1_000_000, risk_per_trade_pct=1.0,
                      max_position_pct=100)
    tight_qty, _, tight_risk = size_position(100, 98, rs, 1_000_000)
    wide_qty, _, wide_risk = size_position(100, 90, rs, 1_000_000)
    assert tight_qty > wide_qty, "a wider stop must get fewer shares"
    assert tight_risk == pytest.approx(wide_risk, rel=0.02), \
        "both trades must risk the same rupees"
    assert tight_risk == pytest.approx(10_000, rel=0.02)


def test_not_equal_rupee_allocation():
    """Two stocks at the same price but different volatility get different
    sizes - the whole point of risk-based sizing."""
    rs = RiskSettings(capital=1_000_000, risk_per_trade_pct=1.0,
                      max_position_pct=100)
    calm, _, _ = size_position(500, 490, rs, 1_000_000)
    wild, _, _ = size_position(500, 450, rs, 1_000_000)
    assert calm != wild
    assert calm * 500 != pytest.approx(wild * 500)


def test_single_position_cap_respected():
    rs = RiskSettings(capital=1_000_000, risk_per_trade_pct=5.0,
                      max_position_pct=10)
    qty, value, _ = size_position(100, 99, rs, 1_000_000)
    assert value <= 100_000 + 100


def test_zero_stop_distance_is_rejected():
    rs = RiskSettings()
    assert size_position(100, 100, rs, 1_000_000)[0] == 0


def test_levels_respect_reward_multiple():
    rs = RiskSettings(stop_method="atr", atr_multiple=2.0, reward_multiple=3.0)
    e, s, t = compute_levels(100, 2.0, "LONG", rs)
    assert s == pytest.approx(96)
    assert t == pytest.approx(112)
    assert (t - e) / (e - s) == pytest.approx(3.0)

    e, s, t = compute_levels(100, 2.0, "SHORT", rs)
    assert s == pytest.approx(104)
    assert t == pytest.approx(88)


def test_atr_fallback_when_missing():
    rs = RiskSettings(stop_method="atr", stop_percent=5.0)
    e, s, t = compute_levels(200, float("nan"), "LONG", rs)
    assert s == pytest.approx(190)


def test_portfolio_summary_flags_daily_limit_breach():
    from app.analytics.recommend import Candidate
    rs = RiskSettings(capital=1_000_000, max_daily_loss_pct=1.0,
                      max_positions=5)

    def mk(sym):
        return Candidate(
            symbol=sym, sector="IT", side="LONG", signal="BUY",
            last_price=100, entry=100, stop=95, target=110,
            risk_per_share=5, reward_per_share=10, rr=2.0, quantity=1000,
            position_value=100_000, capital_at_risk=5_000,
            expected_profit=10_000, expected_loss=5_000,
            probability=Probability(False, None, 0), expected_move_pct=None,
            rsi=55, trend="Uptrend", volume_change_pct=None,
            relative_volume=None, delivery_pct=None, sector_strength="Strong",
            market_alignment="Aligned", score=1.0, rank=1)

    s = portfolio_summary({"long": [mk(f"S{i}") for i in range(5)],
                           "short": []}, rs)
    assert s["positions"] == 5
    assert s["capital_at_risk"] == 25_000
    assert s["within_daily_limit"] is False
    assert "exceeds your daily limit" in s["warning"]


def test_avoid_signals_excluded_from_portfolio():
    from app.analytics.recommend import Candidate
    rs = RiskSettings(capital=1_000_000)

    def mk(sig):
        return Candidate(
            symbol="X" + sig, sector="IT", side="LONG", signal=sig,
            last_price=100, entry=100, stop=95, target=110, risk_per_share=5,
            reward_per_share=10, rr=2.0, quantity=1000, position_value=100_000,
            capital_at_risk=5_000, expected_profit=10_000, expected_loss=5_000,
            probability=Probability(False, None, 0), expected_move_pct=None,
            rsi=55, trend="Uptrend", volume_change_pct=None,
            relative_volume=None, delivery_pct=None, sector_strength="Strong",
            market_alignment="Aligned", score=1.0, rank=1)

    s = portfolio_summary({"long": [mk("BUY"), mk("AVOID")], "short": []}, rs)
    assert s["positions"] == 1
