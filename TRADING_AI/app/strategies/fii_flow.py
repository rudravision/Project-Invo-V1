"""
Strategy 3: FII Flow Reversal.

Foreign investors sell heavily into weakness; domestic institutions absorb
it. Historically, sustained extreme FII selling while DIIs keep buying has
tended to mark the later stages of a decline rather than the start of one.
This strategy watches for that and accumulates the index.

Four phases, exactly as specified:

  ACCUMULATION  FII 20d < -15,000 cr, DII 20d > +10,000 cr, Nifty RSI < 40
  AGGRESSIVE    FII 20d < -25,000 cr, DII buying sustained, VIX > 18
  TRIM          FII 20d turns positive above +10,000 cr, RSI > 65
  EXIT          FII 20d > +25,000 cr and Nifty P/E > 24

Every threshold is a parameter. All of them are somebody's round numbers,
including the spec author's - they were not derived from anything in this
repository, and I have not tuned them, because tuning four thresholds on a
handful of historical episodes is how you manufacture a backtest that never
repeats.

The data requirement is strict on purpose. ``rolling_net`` refuses to return
a 20-day total until it has 20 clean days, so this strategy simply does not
fire on partial data rather than comparing a 6-day sum against a threshold
meant for 20.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from app.analytics.indicators import rsi

from .base import BUY, HOLD, SELL, MarketContext, Signal, Strategy, \
    StrategyResult, register

ACCUMULATION = "ACCUMULATION"
AGGRESSIVE = "AGGRESSIVE_BUY"
TRIM = "TRIM"
EXIT = "EXIT"
NEUTRAL = "NEUTRAL"


@dataclasses.dataclass
class FIIFlowParams:
    window: int = 20
    accumulate_fii_cr: float = -15_000.0
    accumulate_dii_cr: float = 10_000.0
    accumulate_rsi_below: float = 40.0
    aggressive_fii_cr: float = -25_000.0
    aggressive_vix_above: float = 18.0
    aggressive_dii_streak: int = 10
    trim_fii_cr: float = 10_000.0
    trim_rsi_above: float = 65.0
    exit_fii_cr: float = 25_000.0
    exit_pe_above: float = 24.0
    rsi_period: int = 14
    instruments: tuple = ("NIFTYBEES", "JUNIORBEES")


def dii_buying_streak(rows: list[dict]) -> int:
    """Consecutive most-recent days with positive DII net flow."""
    streak = 0
    for r in reversed(rows or []):
        v = r.get("dii_net")
        if v is None or v <= 0:
            break
        streak += 1
    return streak


@register
class FIIFlowStrategy(Strategy):
    name = "fii_flow"
    description = "Accumulate the index when FIIs capitulate and DIIs absorb"
    requires = ("fii_dii_flows", "index_ohlc")

    @staticmethod
    def default_params() -> FIIFlowParams:
        return FIIFlowParams()

    # ------------------------------------------------------------------ #
    def _nifty_rsi(self, ctx: MarketContext) -> float | None:
        from app.analytics.indices import is_nifty50

        idx = ctx.index_daily
        if idx is None or idx.empty:
            return None
        n = idx[idx["index_name"].map(is_nifty50)].copy()
        if n.empty:
            return None
        n["date"] = pd.to_datetime(n["date"])
        n = n[n["date"] <= pd.Timestamp(ctx.as_of)].sort_values("date")
        if len(n) < self.params.rsi_period * 3:
            return None
        r = rsi(pd.Series(n["close"].to_numpy(dtype=float)),
                self.params.rsi_period)
        v = r.iloc[-1]
        return float(v) if np.isfinite(v) else None

    # ------------------------------------------------------------------ #
    def generate(self, ctx: MarketContext) -> StrategyResult:
        p = self.params
        flows = ctx.flows

        if not flows:
            return self._empty(
                ctx.as_of,
                "No FII/DII data has been loaded. Download it, or import the "
                "CSV from nseindia.com, before this strategy can run.")
        if not flows.get("available"):
            return self._empty(
                ctx.as_of,
                flows.get("reason",
                          "Not enough FII/DII history for a rolling total."))

        fii = float(flows["fii_net"])
        dii = float(flows["dii_net"])
        nifty_rsi = self._nifty_rsi(ctx)
        vix = ctx.india_vix
        pe = (ctx.valuation or {}).get("pe")
        streak = dii_buying_streak(flows.get("rows") or [])

        missing = []
        if nifty_rsi is None:
            missing.append("Nifty RSI (needs index history)")
        if vix is None:
            missing.append("India VIX")
        if pe is None:
            missing.append("Nifty P/E")

        metrics = {
            f"fii_{p.window}day_net_cr": round(fii, 2),
            f"dii_{p.window}day_net_cr": round(dii, 2),
            "dii_buying_streak_days": streak,
            "nifty_rsi": round(nifty_rsi, 1) if nifty_rsi is not None else None,
            "india_vix": vix, "nifty_pe": pe,
            "as_of": flows.get("as_of"), "units": flows.get("units"),
        }

        # ---- phase, most extreme first ----------------------------------
        phase, action, alloc, why = NEUTRAL, HOLD, 0.0, ""

        if (fii < p.aggressive_fii_cr and streak >= p.aggressive_dii_streak
                and vix is not None and vix > p.aggressive_vix_above):
            phase, action, alloc = AGGRESSIVE, BUY, 80.0
            why = (f"FIIs have sold Rs {abs(fii):,.0f} cr over {p.window} "
                   f"sessions while DIIs have bought for {streak} days "
                   f"running, with VIX at {vix:.1f}.")
        elif (fii < p.accumulate_fii_cr and dii > p.accumulate_dii_cr
                and nifty_rsi is not None
                and nifty_rsi < p.accumulate_rsi_below):
            phase, action, alloc = ACCUMULATION, BUY, 33.0
            why = (f"FIIs net Rs {fii:,.0f} cr and DIIs net Rs {dii:,.0f} cr "
                   f"over {p.window} sessions, with Nifty RSI at "
                   f"{nifty_rsi:.0f}. Buy in three tranches, not at once.")
        elif (fii > p.exit_fii_cr and pe is not None and pe > p.exit_pe_above):
            phase, action, alloc = EXIT, SELL, 100.0
            why = (f"FIIs have bought Rs {fii:,.0f} cr over {p.window} "
                   f"sessions and the Nifty P/E is {pe}. Move this "
                   f"strategy to cash.")
        elif (fii > p.trim_fii_cr and nifty_rsi is not None
                and nifty_rsi > p.trim_rsi_above):
            phase, action, alloc = TRIM, SELL, 50.0
            why = (f"FII flows have turned positive (Rs {fii:,.0f} cr) with "
                   f"Nifty RSI at {nifty_rsi:.0f}. Reduce by half.")

        if phase == NEUTRAL:
            return StrategyResult(
                strategy=self.name, as_of=str(ctx.as_of),
                skipped_reason=(
                    f"Flows are not at an extreme. FII {p.window}-day net is "
                    f"Rs {fii:,.0f} cr, DII Rs {dii:,.0f} cr. This strategy "
                    f"is expected to fire only two to four times a year."),
                filters_skipped=missing,
                notes=f"Current reading: {metrics}")

        sig = Signal(
            strategy=self.name,
            symbol=p.instruments[0] if action == BUY else "NIFTY 50",
            action=action, allocation_pct=alloc,
            confidence=None,          # not calibrated; do not invent one
            reasoning=why,
            metrics={**metrics, "phase": phase,
                     "recommended_instruments": list(p.instruments)},
            as_of=str(ctx.as_of))

        return StrategyResult(
            strategy=self.name, as_of=str(ctx.as_of), signals=[sig],
            filters_skipped=missing, universe_size=1,
            notes=(f"Phase {phase}. Thresholds are configurable and were "
                   f"not fitted to your data - treat them as rules of "
                   f"thumb, not evidence."))
