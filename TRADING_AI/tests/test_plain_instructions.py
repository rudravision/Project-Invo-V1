"""Plain-English instructions for a beginner.

The danger this guards against is a tidy, confident one-line order produced
by a strategy that loses money, or by a score with no evidence behind it.
These tests check the wording refuses to overstate, states rupee amounts,
and never claims an intraday capability the data cannot support.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.analytics.plain import (HORIZON_TEXT, INTRADAY_NOTE, instruction,
                                 rupees, session_advice)
from tests.test_index_names import j, real_names, recent_end  # noqa: E402,F401


def _cand(**over):
    c = {
        "symbol": "RELIANCE", "side": "LONG", "signal": "BUY",
        "quantity": 40, "entry": 2500.0, "stop": 2400.0, "target": 2700.0,
        "expected_profit": 8000.0, "expected_loss": 4000.0, "rr": 2.0,
        "probability": {"available": True, "display": "56%",
                        "n_observations": 1234, "value": 0.56},
        "confirmation_summary": {"text": "6 of 8 checks agree",
                                 "failed_labels": ["Momentum agrees"],
                                 "unknown_labels": []},
    }
    c.update(over)
    return c


# ------------------------------------------------------------ formatting --
@pytest.mark.parametrize("v,expect", [
    (0, "Rs 0"), (999, "Rs 999"), (1000, "Rs 1,000"),
    (100000, "Rs 1,00,000"),          # Indian grouping, not 100,000
    (1234567, "Rs 12,34,567"),
    (-4000, "-Rs 4,000"), (None, "-"),
])
def test_rupees_uses_indian_grouping(v, expect):
    assert rupees(v) == expect


# ----------------------------------------------------------- the wording --
def test_headline_is_one_actionable_line():
    p = instruction(_cand(), strategy_is_profitable=True)
    assert p.headline.startswith("BUY 40 shares of RELIANCE")
    assert "Rs 2,500" in p.headline
    assert "Rs 1,00,000" in p.headline        # total outlay spelled out
    assert p.tradeable is True


def test_short_trades_say_short_sell_not_buy():
    p = instruction(_cand(side="SHORT", signal="SELL"),
                    strategy_is_profitable=True)
    assert p.headline.startswith("SHORT-SELL")
    assert any("Buy back at" in s for s in p.steps)


def test_steps_give_rupees_and_percent_for_stop_and_target():
    p = instruction(_cand(), strategy_is_profitable=True)
    text = " ".join(p.steps)
    assert "Rs 2,400" in text and "4.0%" in text      # stop
    assert "Rs 2,700" in text and "8.0%" in text      # target
    assert "Rs 4,000" in text                          # rupee loss
    assert "Rs 8,000" in text                          # rupee profit
    assert "stop loss" in text.lower()


def test_stop_loss_instruction_is_immediate_and_fixed():
    p = instruction(_cand(), strategy_is_profitable=True)
    text = " ".join(p.steps).lower()
    assert "immediately" in text
    assert "never move the stop loss" in text


# --------------------------------------------------------- honest limits --
def test_no_probability_means_no_percentage_is_quoted():
    p = instruction(_cand(probability={"available": False,
                                       "display": "Insufficient data",
                                       "n_observations": 0}),
                    strategy_is_profitable=True)
    assert "%" not in p.confidence
    assert "200 past cases" in p.confidence
    assert any("unproven" in w for w in p.warnings)


def test_available_probability_states_the_sample_size():
    p = instruction(_cand(), strategy_is_profitable=True)
    assert "56%" in p.confidence
    assert "1,234" in p.confidence
    assert "not a promise" in p.confidence


def test_losing_strategy_blocks_the_instruction():
    """The most important test here."""
    p = instruction(_cand(), strategy_is_profitable=False)
    assert p.tradeable is False
    assert p.headline.startswith("DO NOT TRADE")
    assert any("LOST money" in w for w in p.warnings)
    assert any("paper" in w.lower() for w in p.warnings)


def test_unrun_backtest_warns_but_does_not_pretend():
    p = instruction(_cand(), strategy_is_profitable=None)
    assert any("has not been run" in w for w in p.warnings)


def test_avoid_signal_is_refused():
    p = instruction(_cand(signal="AVOID"), strategy_is_profitable=True)
    assert p.tradeable is False
    assert "DO NOT TRADE" in p.headline
    assert any("against the overall market" in w for w in p.warnings)


def test_zero_quantity_is_not_presented_as_a_trade():
    p = instruction(_cand(quantity=0), strategy_is_profitable=True)
    assert p.tradeable is False
    assert "No position size fits" in p.headline


def test_horizon_is_next_session_and_never_claims_intraday():
    """EOD data cannot support intraday instructions - the wording must not."""
    p = instruction(_cand(), strategy_is_profitable=True)
    assert p.horizon == HORIZON_TEXT
    assert "next trading session" in p.horizon
    blob = (p.headline + " ".join(p.steps) + p.confidence).lower()
    for word in ("intraday", "minute", "scalp", "within the day"):
        assert word not in blob


def test_intraday_limitation_is_stated_plainly():
    assert "end-of-day" in INTRADAY_NOTE
    assert "cannot" in INTRADAY_NOTE


def test_checks_line_lists_what_disagreed():
    p = instruction(_cand(), strategy_is_profitable=True)
    assert "6 of 8 checks agree" in p.checks
    assert "momentum agrees" in p.checks.lower()


def test_unknown_checks_are_reported_as_uncheckable():
    p = instruction(_cand(confirmation_summary={
        "text": "4 of 6 checks agree", "failed_labels": [],
        "unknown_labels": ["Real buying (delivery %)"]}),
        strategy_is_profitable=True)
    assert "cannot check" in p.checks.lower()


# --------------------------------------------------------- session advice --
def test_advice_when_data_is_blocked():
    a = session_advice(blocked=True, strategy_is_profitable=True,
                       n_long=0, n_short=0)
    assert a["tone"] == "bad"
    assert "REPAIR DATA" in a["text"]


def test_advice_for_a_losing_strategy_says_paper_only():
    a = session_advice(blocked=False, strategy_is_profitable=False,
                       n_long=3, n_short=2)
    assert a["tone"] == "bad"
    assert a["title"] == "Paper trading only"
    assert "not so you can place them" in a["text"]


def test_advice_when_nothing_qualifies_is_reassuring():
    a = session_advice(blocked=False, strategy_is_profitable=True,
                       n_long=0, n_short=0)
    assert "Doing nothing is a position too" in a["text"]


def test_good_advice_repeats_the_intraday_limitation():
    a = session_advice(blocked=False, strategy_is_profitable=True,
                       n_long=3, n_short=2)
    assert a["tone"] == "good"
    assert "end-of-day" in a["text"]


# ------------------------------------------------------------- in the app --
def test_api_attaches_a_plain_instruction_to_every_idea(real_names):
    c, app, days = real_names
    r = j(c.get("/api/recommendations"))
    assert r["blocked"] is False, r.get("reason")
    assert r["advice"]["title"]
    assert "end-of-day" in r["intraday_note"]
    for x in r["long"] + r["short"]:
        p = x["plain"]
        assert p["headline"] and p["confidence"] and p["checks"]
        assert p["horizon"] == HORIZON_TEXT
        # no calibration in this fixture, so no percentage may appear
        assert "%" not in p["confidence"]


def test_api_switches_to_paper_mode_after_a_losing_backtest(real_names,
                                                            tmp_path):
    """Write a losing backtest result and the ideas must stop being orders."""
    c, app, days = real_names
    bdir = Path(app.config["SETTINGS"].root) / "backtests"
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / "20260101_000000_stats.json").write_text(
        json.dumps({"total_return_pct": -15.23}), encoding="utf-8")

    r = j(c.get("/api/recommendations"))
    assert r["strategy_profitable"] is False
    assert r["advice"]["title"] == "Paper trading only"
    for x in r["long"] + r["short"]:
        assert x["plain"]["tradeable"] is False
        assert x["plain"]["headline"].startswith("DO NOT TRADE")


# --------------------------------------------------- the simple screen ----
def _html():
    return (ROOT / "app" / "gui" / "static" / "index.html").read_text(
        encoding="utf-8")


def _js():
    return (ROOT / "app" / "gui" / "static" / "app.js").read_text(
        encoding="utf-8")


def test_today_is_the_first_page_a_user_sees():
    h = _html()
    assert 'id="page-today"' in h
    assert 'class="page active" id="page-today"' in h
    assert 'class="nav active" data-page="today"' in h


def test_only_three_items_are_visible_before_more_options():
    """A beginner should not meet ten pages on launch."""
    h = _html()
    top = h.split('id="advToggle"')[0]
    visible = top.count('class="nav')
    assert visible == 3, f"expected Today/Charts/Settings, found {visible}"
    # the technical pages must still exist, just tucked away
    hidden = h.split('id="advNav"')[1]
    for page in ("heatmap", "backtest", "sources", "logs", "backups"):
        assert f'data-page="{page}"' in hidden


def test_today_page_wires_up_its_buttons():
    js = _js()
    assert "function loadToday()" in js
    assert 'if (page === "today") loadToday();' in js
    # the action buttons must be bound to real jobs, not decorative
    assert js.count("bindToday();") >= 3


def test_today_uses_the_plain_cards_not_the_technical_grid():
    js = _js()
    today = js.split("function loadTodayIdeas()")[1].split("\n  function ")[0]
    assert "pcard" in today          # plain instruction cards
    assert "cell(" not in today      # never the raw RSI/MACD grid
