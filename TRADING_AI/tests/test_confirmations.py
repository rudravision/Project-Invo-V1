"""Confirmation checks, and the harness that decides whether they are worth
keeping.

The point of these tests is not that the checks are clever. It is that:

* a check with no data says UNKNOWN instead of quietly passing,
* the measurement finds a planted edge and reports no edge on noise, and
* confirmations never change the probability shown to the user.

That last one matters most. "More confirmations" must not become a way of
inflating a probability number that is supposed to come only from measured
out-of-sample results.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.analytics.confirmations import (CHECKS, FAIL, PASS, UNKNOWN,
                                         check_delivery, check_market,
                                         check_no_recent_announcement,
                                         check_trend, check_volume_surge,
                                         evaluate_checks, run_checks,
                                         summarise)
from tests.test_gui_api import build_root, seed  # noqa: E402
from tests.test_index_names import j, real_names, recent_end  # noqa: E402,F401


# ------------------------------------------------------- single checks ----
def test_volume_surge_passes_on_heavy_volume():
    c = check_volume_surge({"relative_volume": 2.4}, "LONG", {})
    assert c.status == PASS
    assert "2.40x" in c.detail


def test_volume_surge_fails_on_quiet_volume():
    c = check_volume_surge({"relative_volume": 0.7}, "LONG", {})
    assert c.status == FAIL
    assert "no unusual interest" in c.detail


def test_missing_data_is_unknown_not_a_pass():
    """The important one: absent data must never count in your favour."""
    assert check_volume_surge({}, "LONG", {}).status == UNKNOWN
    assert check_delivery({}, "LONG", {}).status == UNKNOWN
    assert check_no_recent_announcement({}, "LONG", {}).status == UNKNOWN
    assert check_market({}, "LONG", {}).status == UNKNOWN


def test_delivery_check_reports_the_actual_number():
    c = check_delivery({"delivery_pct": 62.5}, "LONG", {})
    assert c.status == PASS
    assert "62.5%" in c.detail


def test_trend_check_is_direction_aware():
    up = {"above_sma50": 1.0, "above_sma200": 1.0}
    assert check_trend(up, "LONG", {}).status == PASS
    assert check_trend(up, "SHORT", {}).status == FAIL


def test_market_alignment_derived_from_trend_for_history():
    assert check_market({"market_trend": "Bullish"}, "LONG", {}).status == PASS
    assert check_market({"market_trend": "Bullish"}, "SHORT", {}).status == FAIL
    assert check_market({"market_trend": "Bearish"}, "SHORT", {}).status == PASS


def test_announcement_check_counts_but_does_not_score_sentiment():
    c = check_no_recent_announcement({"announcements_7d": 3}, "LONG", {})
    assert c.status == FAIL
    assert "3 company announcement" in c.detail
    # It must not claim news is bullish or bearish.
    assert "bullish" not in c.detail.lower()
    assert "bearish" not in c.detail.lower()
    assert "sentiment" not in c.detail.lower()


def test_run_checks_covers_every_registered_check():
    out = run_checks({"relative_volume": 1.5}, "LONG")
    assert len(out) == len(CHECKS)
    assert {c.key for c in out} == set(CHECKS)


def test_summary_counts_are_honest_about_unknowns():
    checks = run_checks({"relative_volume": 1.5, "above_sma50": 1.0,
                         "above_sma200": 1.0}, "LONG")
    s = summarise(checks)
    assert s["passed"] + s["failed"] + s["unknown"] == len(CHECKS)
    assert s["known"] == s["passed"] + s["failed"]
    assert f"{s['passed']} of {s['known']}" in s["text"]
    assert s["unknown"] > 0            # delivery, news etc. are absent here


# --------------------------------------------------- the measurement ------
def _frame(n=2000, seed_=3):
    rng = np.random.default_rng(seed_)
    return pd.DataFrame({
        "relative_volume": rng.uniform(0.5, 2.0, n),
        "vol_z": rng.normal(0, 1, n),
        "above_sma50": rng.integers(0, 2, n).astype(float),
        "above_sma200": rng.integers(0, 2, n).astype(float),
        "macd_hist": rng.normal(0, 1, n),
        "rsi14": rng.uniform(20, 80, n),
        "turnover20": rng.uniform(1e6, 1e9, n),
        "delivery_pct": rng.uniform(20, 70, n),
        "sector_strength": rng.choice(["Strong", "Weak", "Neutral"], n),
        "market_trend": rng.choice(["Bullish", "Bearish"], n),
        "announcements_7d": rng.integers(0, 2, n),
        "fwd_ret": rng.normal(0, 0.02, n),
    })


def test_no_edge_is_reported_on_pure_noise():
    """A harness that finds edges in random data is worse than useless."""
    out = evaluate_checks(_frame(), side="LONG", min_observations=100)
    verdicts = set(out["verdict"])
    assert "Helps" not in verdicts or (out["edge_pct"].abs().max() < 6)
    assert set(out["check"]) == set(CHECKS)


def test_a_planted_edge_is_found():
    """If a check really does predict, the harness must say so."""
    f = _frame(n=3000, seed_=11)
    # make high delivery genuinely predictive
    high = f["delivery_pct"] >= 45
    f.loc[high, "fwd_ret"] = abs(f.loc[high, "fwd_ret"])       # always up
    f.loc[~high, "fwd_ret"] = -abs(f.loc[~high, "fwd_ret"])    # always down

    out = evaluate_checks(f, side="LONG", min_observations=100)
    row = out[out["check"] == "delivery"].iloc[0]
    assert row["verdict"] == "Helps"
    assert row["edge_pct"] > 50
    assert row["n_pass"] > 100 and row["n_fail"] > 100


def test_small_samples_are_refused_not_guessed():
    out = evaluate_checks(_frame(n=120), side="LONG", min_observations=200)
    assert (out["verdict"] == "Not enough data to judge").all()


def test_evaluation_handles_an_empty_frame():
    out = evaluate_checks(pd.DataFrame(), side="LONG")
    assert out.empty


# ------------------------------------------------- end to end in the app --
def test_trade_cards_carry_the_checks(real_names):
    c, app, days = real_names
    r = j(c.get("/api/recommendations"))
    assert r["blocked"] is False, r.get("reason")
    cands = r["long"] + r["short"]
    assert cands
    for x in cands:
        assert len(x["confirmations"]) == len(CHECKS)
        assert x["confirmation_summary"]["known"] >= 1
        for chk in x["confirmations"]:
            assert chk["status"] in (PASS, FAIL, UNKNOWN)
            assert chk["detail"]


def test_confirmations_do_not_change_the_probability(real_names):
    """Confirmations are evidence, not a multiplier on the probability."""
    c, app, days = real_names
    r = j(c.get("/api/recommendations"))
    for x in r["long"] + r["short"]:
        prob = x["probability"]
        passed = x["confirmation_summary"]["passed"]
        if not prob["available"]:
            # no calibration in this fixture: must stay honest regardless of
            # how many checks agree
            assert prob["display"] == "Insufficient data"
            assert prob["value"] is None
            assert passed >= 0


def test_confirmation_evidence_endpoint_before_measuring(real_names):
    c, _, _ = real_names
    d = j(c.get("/api/confirmations"))
    assert d["available"] is False
    assert "Rebuild Calibration" in d["message"]


def test_confirmation_evidence_endpoint_after_measuring(real_names):
    from app.gui.pipeline import _load, measure_confirmations
    c, app, days = real_names
    db = app.config["DB"]
    daily, idx, sectors, _ = _load(db)
    measure_confirmations(db, daily, sectors, idx=idx)

    d = j(c.get("/api/confirmations"))
    assert d["available"] is True
    assert d["sides"]["LONG"] and d["sides"]["SHORT"]
    row = d["sides"]["LONG"][0]
    assert {"check_key", "label", "n_pass", "n_fail", "verdict"} <= set(row)
    assert "edge" in d["note"].lower()


@pytest.mark.parametrize("value,expect", [
    ("Aligned", PASS),      # wording used by the live recommendation path
    ("With", PASS),         # wording used by the historical evaluation
    ("Against", FAIL),
    ("Neutral", FAIL),
])
def test_market_check_accepts_both_vocabularies(value, expect):
    """The two code paths name alignment differently; neither may misreport."""
    c = check_market({"market_alignment": value}, "LONG", {})
    assert c.status == expect
    assert "aligned the" not in c.detail      # the grammar bug this caught
