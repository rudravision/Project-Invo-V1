"""
Strategy 5: RSI Mean Reversion on the index.

Buy the index when it is deeply oversold, exit when it recovers. Few
signals, high conviction - the spec expects 2-5 a year.

Inputs, all free:
  * Nifty 50 closing series      -> RSI(14), RSI(5), 200 DMA   (NSE archive)
  * India VIX                    -> index_ohlc                  (NSE archive)
  * Nifty P/E                    -> market_valuation            (NSE reports)

On the confidence number
------------------------
The specification's example output carries ``"reasoning": "... Historical
win rate: 78% in similar conditions"``. I will not print a number like that
unless it was measured. ``measure_condition`` counts what actually happened
in *your own* downloaded history whenever the same condition occurred, and
reports the sample size alongside. If there are too few past occurrences -
and with 2-5 signals a year there usually are - it says so instead. A
made-up 78% is worse than no number, because you would act on it.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from app.analytics.indicators import rsi, sma

from .base import BUY, HOLD, SELL, MarketContext, Signal, Strategy, \
    StrategyResult, register

MIN_OBSERVATIONS = 30       # below this we refuse to quote a hit rate


@dataclasses.dataclass
class MeanReversionParams:
    rsi_period: int = 14
    rsi_fast: int = 5
    oversold_rsi: float = 30.0
    oversold_rsi_fast: float = 20.0
    extreme_rsi: float = 25.0
    extreme_vix: float = 22.0
    overbought_rsi: float = 75.0
    overbought_rsi_fast: float = 85.0
    overbought_pe: float = 24.0
    near_200dma_pct: float = 5.0     # "within 5% of the 200 DMA or below"
    exit_rsi: float = 55.0
    stop_loss_pct: float = 3.0
    max_hold_days: int = 20
    dma_period: int = 200
    forward_days: int = 10           # horizon used when measuring history


def measure_condition(close: pd.Series, mask: pd.Series,
                      forward_days: int = 10,
                      min_observations: int = MIN_OBSERVATIONS) -> dict:
    """How often did the index rise after this condition, historically?

    Straight counting on the user's own data - no model, no fitting. The
    last `forward_days` rows are excluded because their outcome is not
    known yet.
    """
    if close is None or len(close) < forward_days + 2:
        return {"available": False, "observations": 0,
                "note": "Not enough history to measure this condition."}

    fwd = close.shift(-forward_days) / close - 1.0
    valid = mask & fwd.notna()
    n = int(valid.sum())
    if n < min_observations:
        return {"available": False, "observations": n,
                "note": (f"This condition has only occurred {n} time(s) in "
                         f"your history; at least {min_observations} are "
                         f"needed before a hit rate means anything.")}
    wins = float((fwd[valid] > 0).mean())
    return {"available": True, "observations": n,
            "hit_rate_pct": round(wins * 100, 1),
            "mean_return_pct": round(float(fwd[valid].mean()) * 100, 2),
            "forward_days": forward_days,
            "note": (f"In {n} past occurrences the index was higher "
                     f"{forward_days} sessions later {wins * 100:.0f}% of "
                     f"the time. Past frequency, not a forecast.")}


@register
class MeanReversionStrategy(Strategy):
    name = "mean_reversion"
    description = "Buy the index when RSI is extremely oversold"
    requires = ("index_ohlc",)

    @staticmethod
    def default_params() -> MeanReversionParams:
        return MeanReversionParams()

    # ------------------------------------------------------------------ #
    def _index_series(self, ctx: MarketContext) -> pd.Series | None:
        from app.analytics.indices import is_nifty50

        idx = ctx.index_daily
        if idx is None or idx.empty:
            return None
        n = idx[idx["index_name"].map(is_nifty50)].copy()
        if n.empty:
            return None
        n["date"] = pd.to_datetime(n["date"])
        n = n[n["date"] <= pd.Timestamp(ctx.as_of)].sort_values("date")
        if len(n) < 60:
            return None
        return pd.Series(n["close"].to_numpy(dtype=float),
                         index=pd.DatetimeIndex(n["date"]))

    # ------------------------------------------------------------------ #
    def generate(self, ctx: MarketContext) -> StrategyResult:
        p = self.params
        close = self._index_series(ctx)
        if close is None:
            return self._empty(
                ctx.as_of,
                "No NIFTY 50 index history is available. Run UPDATE & "
                "ANALYZE MARKET, which downloads the index series.")

        r14 = rsi(close, p.rsi_period)
        r5 = rsi(close, p.rsi_fast)
        dma = sma(close, p.dma_period)

        last = close.iloc[-1]
        last_r14 = float(r14.iloc[-1]) if np.isfinite(r14.iloc[-1]) else None
        last_r5 = float(r5.iloc[-1]) if np.isfinite(r5.iloc[-1]) else None
        last_dma = (float(dma.iloc[-1])
                    if len(dma.dropna()) and np.isfinite(dma.iloc[-1])
                    else None)

        if last_r14 is None or last_r5 is None:
            return self._empty(ctx.as_of,
                               "Not enough index history to compute RSI yet.")

        vix = ctx.india_vix
        pe = (ctx.valuation or {}).get("pe")
        dist = ((last / last_dma - 1.0) * 100.0) if last_dma else None

        missing = []
        if vix is None:
            missing.append("India VIX")
        if pe is None:
            missing.append("Nifty P/E")
        if last_dma is None:
            missing.append(f"{p.dma_period} DMA (needs more history)")

        metrics = {
            "nifty_close": round(float(last), 2),
            "rsi_14": round(last_r14, 1), "rsi_5": round(last_r5, 1),
            "india_vix": vix, "nifty_pe": pe,
            "nifty_200dma": round(last_dma, 2) if last_dma else None,
            "distance_from_200dma_pct": round(dist, 2) if dist is not None else None,
        }

        near_dma = (dist is not None and dist <= p.near_200dma_pct)
        below_dma = (dist is not None and dist < 0)

        # ---- extreme oversold ------------------------------------------
        if (last_r14 < p.extreme_rsi and vix is not None
                and vix > p.extreme_vix and below_dma):
            action, label = BUY, "STRONG_BUY"
            cond = (r14 < p.extreme_rsi)
        # ---- ordinary oversold -----------------------------------------
        elif (last_r14 < p.oversold_rsi and last_r5 < p.oversold_rsi_fast
                and near_dma):
            action, label = BUY, "BUY"
            cond = (r14 < p.oversold_rsi) & (r5 < p.oversold_rsi_fast)
        # ---- overbought --------------------------------------------------
        elif (last_r14 > p.overbought_rsi and last_r5 > p.overbought_rsi_fast
                and pe is not None and pe > p.overbought_pe):
            action, label = SELL, "BOOK_PROFITS"
            cond = (r14 > p.overbought_rsi)
        else:
            return StrategyResult(
                strategy=self.name, as_of=str(ctx.as_of),
                skipped_reason=(
                    f"No extreme reading today. RSI(14) is {last_r14:.0f}; "
                    f"this strategy waits for below {p.oversold_rsi:.0f} or "
                    f"above {p.overbought_rsi:.0f}. It is meant to trade "
                    f"only a few times a year."),
                filters_skipped=missing,
                notes=("Nothing to do is the normal state for this "
                       "strategy."))

        evidence = measure_condition(close, cond, p.forward_days)

        entry = round(float(last), 2)
        if action == BUY:
            stop = round(entry * (1 - p.stop_loss_pct / 100.0), 2)
            reason = (f"RSI(14) at {last_r14:.0f} and RSI(5) at "
                      f"{last_r5:.0f}"
                      + (f", India VIX {vix:.1f}" if vix is not None else "")
                      + (f", index {dist:+.1f}% vs its {p.dma_period} DMA"
                         if dist is not None else "")
                      + ". " + evidence["note"])
        else:
            stop = None
            reason = (f"RSI(14) at {last_r14:.0f} with P/E {pe}. "
                      + evidence["note"])

        sig = Signal(
            strategy=self.name, symbol="NIFTY 50", action=action,
            entry_price=entry, stop_loss=stop,
            allocation_pct=100.0 if label == "STRONG_BUY" else 50.0,
            confidence=None,          # never invented; see evidence instead
            horizon_days=p.max_hold_days,
            reasoning=reason,
            metrics={**metrics, "signal_label": label,
                     "exit_condition": f"RSI({p.rsi_period}) > {p.exit_rsi:.0f}",
                     "evidence": evidence},
            as_of=str(ctx.as_of))

        return StrategyResult(strategy=self.name, as_of=str(ctx.as_of),
                              signals=[sig], filters_skipped=missing,
                              universe_size=1,
                              notes=(f"Exit when RSI({p.rsi_period}) crosses "
                                     f"{p.exit_rsi:.0f}, or after "
                                     f"{p.max_hold_days} sessions, or on the "
                                     f"{p.stop_loss_pct:.0f}% stop."))
