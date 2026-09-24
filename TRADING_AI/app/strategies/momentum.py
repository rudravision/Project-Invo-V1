"""
Strategy 1: Momentum Factor (12-1).

Rank the universe by return from T-252 to T-21 - that is, twelve months of
return with the most recent month deliberately left out, because short-term
reversal tends to pollute the last few weeks. Hold the top names, rebalance
monthly, and refuse to churn: a stock already held stays until it falls out
of a wider band.

Everything is configurable (spec rule 2). Nothing below is hardcoded.

On the filters
--------------
The specification asks for five filters. Two of them need data this system
does not currently hold:

* market capitalisation - not downloaded anywhere
* the F&O ban list - not downloaded anywhere

Rather than quietly skip them, every result carries `filters_applied` and
`filters_skipped`, so you always know whether you are looking at a fully
filtered universe or a partly filtered one. Believing a filter ran when it
did not is how a "large-cap momentum" strategy ends up holding illiquid
small caps.

On the expected returns in the specification
--------------------------------------------
The spec lists "CAGR 25-40%, Sharpe 1.2-1.8". Those are someone's hopes,
not a contract. This module does not tune itself toward them, and the
backtest reports whatever actually happened.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd

from .base import BUY, HOLD, SELL, MarketContext, Signal, Strategy, \
    StrategyResult, register

TRADING_DAYS_YEAR = 252


@dataclasses.dataclass
class MomentumParams:
    lookback_days: int = 252         # 12 months
    skip_days: int = 21              # skip the most recent month
    top_n: int = 20                  # how many to hold
    exit_rank: int = 30              # sell only when it drops past this
    stop_loss_pct: float = 10.0      # from entry
    min_price: float = 50.0          # no penny stocks
    min_turnover_cr: float = 5.0     # 20-day average daily turnover
    min_delivery_pct: float = 40.0   # real buying, if we have the data
    min_history_days: int = 273      # lookback + skip
    allocation_pct_each: float | None = None   # default: equal weight


@register
class MomentumStrategy(Strategy):
    name = "momentum"
    description = "12-1 price momentum, monthly rebalance, top 20 equal weight"
    requires = ("daily_ohlc",)

    @staticmethod
    def default_params() -> MomentumParams:
        return MomentumParams()

    # ------------------------------------------------------------------ #
    def scores(self, ctx: MarketContext) -> pd.DataFrame:
        """12-1 return per symbol, plus the numbers the filters need.

        Returns one row per eligible symbol. Symbols without enough history
        are absent rather than scored as zero.
        """
        p = self.params
        d = ctx.daily
        if d is None or d.empty:
            return pd.DataFrame()

        d = d.copy()
        d["date"] = pd.to_datetime(d["date"])
        d = d[d["date"] <= pd.Timestamp(ctx.as_of)]
        need = p.lookback_days + p.skip_days

        rows = []
        for sym, g in d.groupby("symbol", sort=False):
            g = g.sort_values("date")
            if len(g) < max(need, p.min_history_days):
                continue
            close = g["close"].to_numpy(dtype=float)
            start = close[-need]
            end = close[-(p.skip_days + 1)]
            if not np.isfinite(start) or not np.isfinite(end) or start <= 0:
                continue

            vol = g["volume"].to_numpy(dtype=float)[-20:]
            px = close[-20:]
            turnover_cr = float(np.nanmean(px * vol)) / 1e7 if len(px) else float("nan")

            rows.append({
                "symbol": sym,
                "ret_12_1": (end / start - 1.0) * 100.0,
                "last_price": float(close[-1]),
                "turnover_cr": turnover_cr,
                "delivery_pct": ctx.delivery.get(sym),
                "bars": len(g),
            })

        if not rows:
            return pd.DataFrame()
        out = pd.DataFrame(rows).sort_values("ret_12_1", ascending=False)
        out["rank"] = range(1, len(out) + 1)
        return out.reset_index(drop=True)

    # ------------------------------------------------------------------ #
    def _filter(self, df: pd.DataFrame, ctx: MarketContext):
        p = self.params
        applied, skipped = [], []

        m = pd.Series(True, index=df.index)

        m &= df["last_price"] >= p.min_price
        applied.append(f"price >= Rs {p.min_price:.0f}")

        if df["turnover_cr"].notna().any():
            m &= df["turnover_cr"] >= p.min_turnover_cr
            applied.append(f"20-day turnover >= Rs {p.min_turnover_cr:.0f} cr")
        else:
            skipped.append("liquidity (no volume data)")

        if df["delivery_pct"].notna().any():
            # Only filter the rows we actually have delivery for; a missing
            # value must not silently eliminate a stock.
            known = df["delivery_pct"].notna()
            m &= (~known) | (df["delivery_pct"] >= p.min_delivery_pct)
            applied.append(f"delivery >= {p.min_delivery_pct:.0f}% where known")
        else:
            skipped.append("delivery % (not downloaded)")

        # Specified but impossible with the data we hold. Say so.
        skipped.append("market cap > Rs 1,000 cr (market cap not downloaded)")
        skipped.append("F&O ban list (not downloaded)")

        return df[m].copy(), applied, skipped

    # ------------------------------------------------------------------ #
    def generate(self, ctx: MarketContext) -> StrategyResult:
        p = self.params
        scored = self.scores(ctx)
        if scored.empty:
            return self._empty(
                ctx.as_of,
                f"No stock has the {p.lookback_days + p.skip_days} sessions "
                f"of history this strategy needs. Download more data.")

        eligible, applied, skipped = self._filter(scored, ctx)
        if eligible.empty:
            return self._empty(ctx.as_of,
                               "Every stock was removed by the filters.",
                               filters_applied=applied,
                               filters_skipped=skipped,
                               universe_size=len(scored))

        eligible = eligible.reset_index(drop=True)
        eligible["rank"] = range(1, len(eligible) + 1)
        held = set(ctx.holdings or {})
        top = eligible.head(p.top_n)
        keep_band = eligible.head(p.exit_rank)
        keep_syms = set(keep_band["symbol"])

        alloc = (p.allocation_pct_each
                 if p.allocation_pct_each is not None
                 else round(100.0 / max(p.top_n, 1), 4))

        signals: list[Signal] = []

        # BUY the newcomers, HOLD the ones already owned and still ranked.
        for r in top.itertuples():
            already = r.symbol in held
            # Round the entry first, then derive the stop from it, so the
            # two numbers on screen are consistent with each other.
            entry = round(float(r.last_price), 2)
            stop = round(entry * (1 - p.stop_loss_pct / 100.0), 2)
            signals.append(Signal(
                strategy=self.name, symbol=r.symbol,
                action=HOLD if already else BUY,
                entry_price=entry,
                stop_loss=stop, target=None,
                allocation_pct=alloc, rank=int(r.rank),
                confidence=None,          # see note below
                horizon_days=None,
                reasoning=(f"Rank {int(r.rank)} of {len(eligible)} by 12-1 "
                           f"momentum ({r.ret_12_1:+.1f}% from "
                           f"{p.lookback_days} to {p.skip_days} sessions "
                           f"ago)."
                           + ("" if not already else
                              " Already held and still in the top "
                              f"{p.top_n}, so no action.")),
                metrics={"ret_12_1_pct": round(float(r.ret_12_1), 2),
                         "turnover_cr": (None if not math.isfinite(r.turnover_cr)
                                         else round(float(r.turnover_cr), 2)),
                         "delivery_pct": r.delivery_pct},
                as_of=str(ctx.as_of)))

        # SELL anything held that has fallen out of the wider band.
        for sym in sorted(held - keep_syms):
            row = eligible[eligible["symbol"] == sym]
            rank = int(row["rank"].iloc[0]) if len(row) else None
            signals.append(Signal(
                strategy=self.name, symbol=sym, action=SELL,
                rank=rank, as_of=str(ctx.as_of),
                reasoning=(f"Dropped out of the top {p.exit_rank} "
                           + (f"(now rank {rank})." if rank
                              else "(no longer in the eligible universe)."))))

        return StrategyResult(
            strategy=self.name, as_of=str(ctx.as_of), signals=signals,
            filters_applied=applied, filters_skipped=skipped,
            universe_size=len(eligible),
            notes=(f"Equal weight {alloc:.2f}% of this strategy's capital "
                   f"per name. Stop loss {p.stop_loss_pct:.0f}% below entry. "
                   f"Holds are not re-bought."))


def is_rebalance_day(today, sessions) -> bool:
    """True on the first trading day of a month (spec: monthly rebalance).

    `sessions` is the list of real session dates, so this is correct across
    holidays - the 1st of the month is frequently not a trading day.
    """
    import datetime as _dt

    if not sessions:
        return False
    today = today if isinstance(today, _dt.date) else \
        pd.Timestamp(today).date()
    same_month = [pd.Timestamp(s).date() for s in sessions
                  if pd.Timestamp(s).year == today.year
                  and pd.Timestamp(s).month == today.month]
    return bool(same_month) and today == min(same_month)
