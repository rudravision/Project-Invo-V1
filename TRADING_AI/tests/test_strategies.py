"""LAKSHMI Phase 2: strategy engine and Strategy 1 (Momentum).

The tests that matter most here are the ones that stop a strategy from
lying:

* the 12-1 calculation must genuinely skip the most recent month,
* a strategy must never be handed data past `as_of`,
* filters that could not be applied must be reported, not dropped,
* one broken strategy must not take the other five down,
* holdings must not churn every month.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.strategies import (BUY, HOLD, SELL, MarketContext, Signal, Strategy,
                            StrategyResult, available, build, register,
                            run_all)
from app.strategies.momentum import (MomentumParams, MomentumStrategy,
                                     is_rebalance_day)


# --------------------------------------------------------------- fixtures --
def make_daily(specs: dict[str, float], n_days: int = 320,
               end: dt.date | None = None, start_price: float = 100.0,
               volume: float = 2_000_000) -> pd.DataFrame:
    """Build price history where each symbol compounds at a fixed daily rate.

    A deterministic ramp makes the ranking predictable, which is the only
    way to assert that 12-1 is being computed the way the spec describes.
    """
    end = end or dt.date(2026, 9, 18)
    days = []
    d = end
    while len(days) < n_days:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    days = sorted(days)

    rows = []
    for sym, rate in specs.items():
        p = start_price
        for x in days:
            p *= (1.0 + rate)
            rows.append({"symbol": sym, "date": x.isoformat(),
                         "open": p, "high": p * 1.01, "low": p * 0.99,
                         "close": p, "volume": volume})
    return pd.DataFrame(rows)


def ctx_for(df: pd.DataFrame, as_of: dt.date | None = None, **kw):
    as_of = as_of or pd.to_datetime(df["date"]).max().date()
    return MarketContext(as_of=as_of, daily=df, **kw)


# ------------------------------------------------------------- the basics --
def test_momentum_is_registered():
    assert "momentum" in available()
    assert isinstance(build("momentum"), MomentumStrategy)


def test_unknown_strategy_names_are_rejected_clearly():
    with pytest.raises(KeyError, match="Unknown strategy"):
        build("does_not_exist")


def test_every_parameter_is_configurable():
    """Spec rule 2: no magic numbers buried in the logic."""
    p = MomentumParams(top_n=5, stop_loss_pct=7.5, min_price=10.0)
    s = build("momentum", params=p)
    assert s.params.top_n == 5 and s.params.stop_loss_pct == 7.5


# ------------------------------------------------------- the 12-1 formula --
def test_ranking_follows_twelve_month_return():
    df = make_daily({"FAST": 0.0020, "MID": 0.0010, "SLOW": 0.0002})
    out = MomentumStrategy().scores(ctx_for(df))
    assert list(out["symbol"]) == ["FAST", "MID", "SLOW"]
    assert list(out["rank"]) == [1, 2, 3]


def test_the_most_recent_month_is_excluded():
    """A stock that only rallied in the last three weeks must not rank top.

    This is the whole point of 12-1. If the skip window were ignored, the
    late spike would dominate.
    """
    df = make_daily({"STEADY": 0.0015, "LATESPIKE": 0.0001})
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    last_15 = sorted(d["date"].unique())[-15:]
    spike = d["symbol"].eq("LATESPIKE") & d["date"].isin(last_15)
    d.loc[spike, "close"] *= 3.0            # a huge, very recent move
    d["date"] = d["date"].dt.strftime("%Y-%m-%d")

    out = MomentumStrategy().scores(ctx_for(d))
    assert out.iloc[0]["symbol"] == "STEADY", \
        "the skip window is not being applied"


def test_symbols_without_enough_history_are_absent_not_zero():
    long_df = make_daily({"LONG": 0.001}, n_days=320)
    short_df = make_daily({"SHORT": 0.001}, n_days=60)
    out = MomentumStrategy().scores(ctx_for(pd.concat([long_df, short_df])))
    assert set(out["symbol"]) == {"LONG"}


def test_no_history_at_all_is_a_clean_skip_not_a_crash():
    res = MomentumStrategy().generate(
        MarketContext(as_of=dt.date(2026, 9, 18), daily=pd.DataFrame()))
    assert res.ok is False
    assert "history" in res.skipped_reason.lower()
    assert res.signals == []


# ------------------------------------------------------------- look-ahead --
def test_context_rejects_future_data():
    df = make_daily({"A": 0.001})
    c = ctx_for(df, as_of=dt.date(2026, 1, 1))
    with pytest.raises(ValueError, match="never see the future"):
        c.assert_no_lookahead()


def test_scores_ignore_rows_after_as_of():
    """An earlier as_of must price the stock as it stood on that day."""
    df = make_daily({"A": 0.001, "B": 0.0005}, n_days=400)
    dates = sorted(pd.to_datetime(df["date"]).dt.date.unique())
    cut = dates[-40]

    full = MomentumStrategy().scores(ctx_for(df)).set_index("symbol")
    trimmed = MomentumStrategy().scores(
        ctx_for(df, as_of=cut)).set_index("symbol")

    assert trimmed.loc["A", "last_price"] < full.loc["A", "last_price"]
    # dates[-40] is itself included, so 39 sessions are excluded
    assert trimmed.loc["A", "bars"] == full.loc["A", "bars"] - 39


# ---------------------------------------------------------------- filters --
def test_penny_stocks_are_filtered_out():
    df = make_daily({"GOOD": 0.001, "PENNY": 0.001}, start_price=100.0)
    d = df.copy()
    d.loc[d["symbol"].eq("PENNY"), ["open", "high", "low", "close"]] *= 0.05
    res = MomentumStrategy().generate(ctx_for(d))
    assert "PENNY" not in {s.symbol for s in res.signals}
    assert any("price >=" in f for f in res.filters_applied)


def test_illiquid_stocks_are_filtered_out():
    df = make_daily({"LIQUID": 0.001, "THIN": 0.0012})
    d = df.copy()
    d.loc[d["symbol"].eq("THIN"), "volume"] = 100      # tiny turnover
    res = MomentumStrategy().generate(ctx_for(d))
    syms = {s.symbol for s in res.signals}
    assert "LIQUID" in syms and "THIN" not in syms


def test_filters_that_cannot_run_are_reported_not_hidden():
    """You must never believe a filter ran when the data was absent."""
    df = make_daily({"A": 0.001})
    res = MomentumStrategy().generate(ctx_for(df))
    joined = " ".join(res.filters_skipped).lower()
    assert "market cap" in joined
    assert "ban list" in joined
    assert "delivery" in joined          # no delivery data in this context


def test_delivery_filter_applies_when_the_data_exists():
    df = make_daily({"REAL": 0.001, "CHURN": 0.0012})
    res = MomentumStrategy().generate(
        ctx_for(df, delivery={"REAL": 65.0, "CHURN": 12.0}))
    syms = {s.symbol for s in res.signals}
    assert "REAL" in syms and "CHURN" not in syms
    assert any("delivery" in f for f in res.filters_applied)


def test_a_stock_with_no_delivery_figure_is_not_silently_dropped():
    df = make_daily({"KNOWN": 0.001, "UNKNOWN": 0.0012})
    res = MomentumStrategy().generate(
        ctx_for(df, delivery={"KNOWN": 70.0}))
    assert "UNKNOWN" in {s.symbol for s in res.signals}


# ------------------------------------------------------------- signalling --
def test_top_n_buys_with_equal_weight_and_a_stop():
    df = make_daily({f"S{i:02d}": 0.002 - i * 0.0001 for i in range(10)})
    res = MomentumStrategy(MomentumParams(top_n=3)).generate(ctx_for(df))
    buys = [s for s in res.signals if s.action == BUY]
    assert len(buys) == 3
    assert {round(s.allocation_pct, 2) for s in buys} == {33.33}
    for s in buys:
        assert s.stop_loss == round(s.entry_price * 0.9, 2)
        assert s.reasoning and s.rank


def test_held_names_still_ranked_are_held_not_rebought():
    """Churn is the enemy: costs are charged per trade."""
    df = make_daily({f"S{i:02d}": 0.002 - i * 0.0001 for i in range(10)})
    c = ctx_for(df, holdings={"S00": {"quantity": 10}})
    res = MomentumStrategy(MomentumParams(top_n=3)).generate(c)
    s00 = [s for s in res.signals if s.symbol == "S00"][0]
    assert s00.action == HOLD
    assert "no action" in s00.reasoning.lower()


def test_a_holding_is_only_sold_once_it_leaves_the_wider_band():
    df = make_daily({f"S{i:02d}": 0.002 - i * 0.0002 for i in range(10)})
    p = MomentumParams(top_n=2, exit_rank=5)

    inside = MomentumStrategy(p).generate(
        ctx_for(df, holdings={"S03": {"quantity": 1}}))
    assert not [s for s in inside.signals
                if s.symbol == "S03" and s.action == SELL]

    outside = MomentumStrategy(p).generate(
        ctx_for(df, holdings={"S08": {"quantity": 1}}))
    sells = [s for s in outside.signals if s.action == SELL]
    assert [s.symbol for s in sells] == ["S08"]
    assert "top 5" in sells[0].reasoning


def test_momentum_never_invents_a_confidence_number():
    """Nothing has been calibrated for this strategy yet, so no score."""
    df = make_daily({"A": 0.001, "B": 0.0005})
    res = MomentumStrategy().generate(ctx_for(df))
    assert all(s.confidence is None for s in res.signals)


# ------------------------------------------------------------- rebalance ---
def test_rebalance_only_on_the_first_trading_day_of_a_month():
    sessions = [dt.date(2026, 9, d) for d in (1, 2, 3, 4, 7, 8)]
    assert is_rebalance_day(dt.date(2026, 9, 1), sessions) is True
    assert is_rebalance_day(dt.date(2026, 9, 2), sessions) is False


def test_rebalance_day_handles_a_holiday_on_the_first():
    """1 Oct is a holiday here, so the 3rd is the first trading day."""
    sessions = [dt.date(2026, 10, d) for d in (3, 4, 5, 6)]
    assert is_rebalance_day(dt.date(2026, 10, 3), sessions) is True
    assert is_rebalance_day(dt.date(2026, 10, 1), sessions) is False


def test_rebalance_day_with_no_sessions_is_false():
    assert is_rebalance_day(dt.date(2026, 9, 1), []) is False


# ----------------------------------------------------------------- runner --
def test_one_broken_strategy_does_not_stop_the_others():
    @register
    class Exploding(Strategy):
        name = "exploding_test_only"

        def generate(self, ctx):
            raise RuntimeError("boom")

    df = make_daily({"A": 0.001})
    out = run_all(ctx_for(df), names=["momentum", "exploding_test_only"])
    assert out["momentum"].ok is True
    assert out["exploding_test_only"].ok is False
    assert "boom" in out["exploding_test_only"].skipped_reason


def test_a_strategy_can_be_switched_off_individually():
    df = make_daily({"A": 0.001})
    out = run_all(ctx_for(df), names=["momentum"],
                  enabled_map={"momentum": False})
    assert out["momentum"].ok is False
    assert "Disabled" in out["momentum"].skipped_reason


def test_result_serialises_for_the_api():
    df = make_daily({f"S{i:02d}": 0.002 - i * 0.0001 for i in range(5)})
    d = MomentumStrategy(MomentumParams(top_n=2)).generate(ctx_for(df)).to_dict()
    assert d["ok"] is True
    assert isinstance(d["signals"], list) and d["signals"]
    assert {"symbol", "action", "entry_price", "stop_loss"} <= set(
        d["signals"][0])


# =========================================================================
# Strategy 5: RSI Mean Reversion
# =========================================================================
from app.strategies.fii_flow import (FIIFlowParams, FIIFlowStrategy,
                                     dii_buying_streak)
from app.strategies.mean_reversion import (MeanReversionParams,
                                           MeanReversionStrategy,
                                           measure_condition)


def index_frame(closes, name="Nifty 50", end=dt.date(2026, 9, 18)):
    days, d = [], end
    while len(days) < len(closes):
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    days = sorted(days)
    return pd.DataFrame([{"index_name": name, "date": x.isoformat(),
                          "close": c} for x, c in zip(days, closes)])


def falling_index(n=400, start=25000.0, rate=-0.0035):
    """A steady decline drives RSI to an extreme."""
    out, p = [], start
    for _ in range(n):
        p *= (1 + rate)
        out.append(p)
    return out


def test_mean_reversion_stays_quiet_in_normal_conditions():
    flat = [20000 + (i % 7) * 10 for i in range(400)]
    res = MeanReversionStrategy().generate(
        MarketContext(as_of=dt.date(2026, 9, 18), daily=pd.DataFrame(),
                      index_daily=index_frame(flat)))
    assert res.ok is False
    assert "No extreme reading" in res.skipped_reason
    assert "only a few times a year" in res.skipped_reason


def test_mean_reversion_fires_when_oversold():
    idx = index_frame(falling_index())
    res = MeanReversionStrategy().generate(
        MarketContext(as_of=dt.date(2026, 9, 18), daily=pd.DataFrame(),
                      index_daily=idx, india_vix=25.0,
                      valuation={"pe": 18.0}))
    assert res.ok is True
    s = res.signals[0]
    assert s.action == BUY and s.symbol == "NIFTY 50"
    assert s.metrics["signal_label"] in ("BUY", "STRONG_BUY")
    assert s.stop_loss == round(s.entry_price * 0.97, 2)
    assert s.metrics["rsi_14"] < 30


def test_mean_reversion_reports_missing_inputs():
    idx = index_frame(falling_index())
    res = MeanReversionStrategy().generate(
        MarketContext(as_of=dt.date(2026, 9, 18), daily=pd.DataFrame(),
                      index_daily=idx))            # no VIX, no PE
    joined = " ".join(res.filters_skipped)
    assert "India VIX" in joined and "P/E" in joined


def test_mean_reversion_without_index_data_explains_itself():
    res = MeanReversionStrategy().generate(
        MarketContext(as_of=dt.date(2026, 9, 18), daily=pd.DataFrame()))
    assert res.ok is False
    assert "UPDATE & ANALYZE MARKET" in res.skipped_reason


def test_mean_reversion_never_invents_a_confidence():
    idx = index_frame(falling_index())
    res = MeanReversionStrategy().generate(
        MarketContext(as_of=dt.date(2026, 9, 18), daily=pd.DataFrame(),
                      index_daily=idx, india_vix=25.0,
                      valuation={"pe": 18.0}))
    assert res.signals[0].confidence is None


def test_measured_hit_rate_refuses_a_small_sample():
    close = pd.Series(np.linspace(100, 120, 60))
    mask = pd.Series([False] * 55 + [True] * 5)
    out = measure_condition(close, mask, forward_days=10)
    assert out["available"] is False
    assert "only occurred" in out["note"]
    assert "hit_rate_pct" not in out


def test_measured_hit_rate_counts_real_outcomes():
    """A rising series must measure a high hit rate, not a guessed one."""
    close = pd.Series(np.linspace(100, 300, 400))
    mask = pd.Series([True] * 400)
    out = measure_condition(close, mask, forward_days=10)
    assert out["available"] is True
    assert out["hit_rate_pct"] == 100.0
    assert out["observations"] == 390       # last 10 have no outcome yet
    assert "not a forecast" in out["note"]


# =========================================================================
# Strategy 3: FII Flow Reversal
# =========================================================================
def flows(fii, dii, rows=None, available=True, window=20):
    return {"available": available, "window": window, "fii_net": fii,
            "dii_net": dii, "as_of": "2026-09-18", "units": "INR crore",
            "rows": rows or [{"dii_net": 500.0} for _ in range(window)]}


def test_fii_strategy_needs_data_before_it_speaks():
    res = FIIFlowStrategy().generate(
        MarketContext(as_of=dt.date(2026, 9, 18), daily=pd.DataFrame()))
    assert res.ok is False
    assert "nseindia.com" in res.skipped_reason


def test_fii_strategy_respects_the_short_window_refusal():
    """A 6-day sum must never be judged against a 20-day threshold."""
    res = FIIFlowStrategy().generate(MarketContext(
        as_of=dt.date(2026, 9, 18), daily=pd.DataFrame(),
        flows={"available": False, "observations": 6,
               "reason": "Only 6 day(s) of FII/DII data stored; 20 needed."}))
    assert res.ok is False
    assert "20 needed" in res.skipped_reason


def test_accumulation_phase():
    idx = index_frame(falling_index())
    res = FIIFlowStrategy().generate(MarketContext(
        as_of=dt.date(2026, 9, 18), daily=pd.DataFrame(), index_daily=idx,
        flows=flows(-18_500.0, 14_200.0), india_vix=19.5))
    assert res.ok is True
    s = res.signals[0]
    assert s.metrics["phase"] == "ACCUMULATION"
    assert s.action == BUY and s.allocation_pct == 33.0
    assert "three tranches" in s.reasoning


def test_aggressive_phase_needs_the_dii_streak_and_vix():
    idx = index_frame(falling_index())
    base = dict(as_of=dt.date(2026, 9, 18), daily=pd.DataFrame(),
                index_daily=idx)

    hit = FIIFlowStrategy().generate(MarketContext(
        **base, flows=flows(-30_000.0, 20_000.0), india_vix=21.0))
    assert hit.signals[0].metrics["phase"] == "AGGRESSIVE_BUY"
    assert hit.signals[0].allocation_pct == 80.0

    # same flows but calm VIX -> must fall back, not claim the extreme
    calm = FIIFlowStrategy().generate(MarketContext(
        **base, flows=flows(-30_000.0, 20_000.0), india_vix=12.0))
    assert calm.signals == [] or \
        calm.signals[0].metrics["phase"] != "AGGRESSIVE_BUY"


def test_exit_phase_on_euphoria():
    rising = index_frame([20000 * (1.004 ** i) for i in range(400)])
    res = FIIFlowStrategy().generate(MarketContext(
        as_of=dt.date(2026, 9, 18), daily=pd.DataFrame(), index_daily=rising,
        flows=flows(30_000.0, -5_000.0), valuation={"pe": 26.0}))
    s = res.signals[0]
    assert s.metrics["phase"] == "EXIT"
    assert s.action == SELL and s.allocation_pct == 100.0


def test_neutral_flows_produce_nothing():
    idx = index_frame(falling_index())
    res = FIIFlowStrategy().generate(MarketContext(
        as_of=dt.date(2026, 9, 18), daily=pd.DataFrame(), index_daily=idx,
        flows=flows(-2_000.0, 1_000.0), india_vix=14.0))
    assert res.ok is False
    assert "two to four times a year" in res.skipped_reason


@pytest.mark.parametrize("nets,expect", [
    ([100, 200, 300], 3),
    ([-50, 200, 300], 2),
    ([100, 200, -1], 0),
    ([100, None, 300], 1),
    ([], 0),
])
def test_dii_streak_counting(nets, expect):
    assert dii_buying_streak([{"dii_net": v} for v in nets]) == expect


def test_fii_thresholds_are_configurable():
    p = FIIFlowParams(accumulate_fii_cr=-5_000.0, accumulate_rsi_below=80.0)
    idx = index_frame(falling_index())
    res = FIIFlowStrategy(p).generate(MarketContext(
        as_of=dt.date(2026, 9, 18), daily=pd.DataFrame(), index_daily=idx,
        flows=flows(-6_000.0, 12_000.0)))
    assert res.ok is True
    assert res.signals[0].metrics["phase"] == "ACCUMULATION"


def test_all_three_strategies_run_together():
    df = make_daily({f"S{i:02d}": 0.002 - i * 0.0001 for i in range(5)})
    idx = index_frame(falling_index())
    ctx = MarketContext(as_of=dt.date(2026, 9, 18), daily=df,
                        index_daily=idx, flows=flows(-18_500.0, 14_200.0),
                        india_vix=19.5, valuation={"pe": 18.0})
    out = run_all(ctx)
    assert set(out) >= {"momentum", "mean_reversion", "fii_flow"}
    assert out["momentum"].ok is True
    assert out["fii_flow"].ok is True


# =========================================================================
# In the application
# =========================================================================
from tests.test_gui_api import build_root, seed          # noqa: E402
from tests.test_index_names import j, recent_end          # noqa: E402
from app.gui.server import create_app                     # noqa: E402


@pytest.fixture()
def app_with_data(tmp_path):
    app = create_app(str(build_root(tmp_path)))
    app.config["TESTING"] = True
    seed(app, n_syms=8, n_days=400, end=recent_end())
    return app


def test_strategy_endpoint_before_any_run(app_with_data):
    d = j(app_with_data.test_client().get("/api/strategies"))
    assert d["available"] is False
    assert set(d["known"]) >= {"momentum", "mean_reversion", "fii_flow"}
    assert all(d["enabled"].values())
    assert "RUN STRATEGIES" in d["message"]


def test_each_strategy_can_be_toggled_independently(app_with_data):
    c = app_with_data.test_client()
    assert j(c.post("/api/strategies/momentum/enabled",
                    json={"enabled": False}))["enabled"] is False
    d = j(c.get("/api/strategies"))
    assert d["enabled"]["momentum"] is False
    assert d["enabled"]["fii_flow"] is True          # untouched


def test_unknown_strategy_toggle_is_404(app_with_data):
    r = app_with_data.test_client().post("/api/strategies/nope/enabled",
                                         json={"enabled": True})
    assert r.status_code == 404


def test_strategy_job_runs_and_is_served_back(app_with_data):
    from app.gui.jobs import Job
    from app.gui.pipeline import run_strategies_job

    out = run_strategies_job(Job(id="s", name="s"),
                             app_with_data.config["DB"],
                             app_with_data.config["SETTINGS"], {})
    assert set(out["ran"]) >= {"momentum", "mean_reversion", "fii_flow"}

    served = j(app_with_data.test_client().get("/api/strategies"))
    assert served["available"] is True
    assert served["as_of"] == out["as_of"]


def test_disabled_strategy_is_skipped_by_the_job(app_with_data):
    from app.gui.jobs import Job
    from app.gui.pipeline import run_strategies_job

    app_with_data.test_client().post("/api/strategies/momentum/enabled",
                                     json={"enabled": False})
    out = run_strategies_job(Job(id="s", name="s"),
                             app_with_data.config["DB"],
                             app_with_data.config["SETTINGS"], {})
    assert out["strategies"]["momentum"]["ok"] is False
    assert "Disabled" in out["strategies"]["momentum"]["skipped_reason"]


def test_context_built_from_the_database_has_no_lookahead(app_with_data):
    from app.gui.pipeline import build_market_context

    ctx = build_market_context(app_with_data.config["DB"],
                               app_with_data.config["SETTINGS"])
    ctx.assert_no_lookahead()          # must not raise
    assert ctx.as_of is not None


def test_strategy_job_without_data_says_what_to_press(tmp_path):
    from app.gui.jobs import Job
    from app.gui.pipeline import run_strategies_job

    app = create_app(str(build_root(tmp_path)))
    with pytest.raises(ValueError, match="UPDATE & ANALYZE MARKET"):
        run_strategies_job(Job(id="s", name="s"), app.config["DB"],
                           app.config["SETTINGS"], {})
