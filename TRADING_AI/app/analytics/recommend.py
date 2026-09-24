"""
Trade candidate generation, levels and position sizing (spec items 7 & 8).

Position sizing is risk-based, NOT equal-rupee. The quantity for each trade
is derived from how far away the stop is:

    risk per trade (Rs) = capital x risk_pct
    quantity            = risk per trade / (entry - stop)

so a volatile stock with a wide stop gets FEWER shares than a quiet one,
and every open position risks the same rupee amount. That is the whole point:
allocating Rs 1 lakh to each name would mean the volatile stock quietly
carries three times the risk of the quiet one.
"""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Any

import numpy as np
import pandas as pd

from .indicators import add_indicator_set
from .probability import Calibrator, Probability, INSUFFICIENT


# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class RiskSettings:
    capital: float = 1_000_000.0
    risk_per_trade_pct: float = 1.0      # % of capital risked per position
    max_positions: int = 5
    max_daily_loss_pct: float = 3.0
    direction: str = "both"              # long | short | both
    stop_method: str = "atr"             # atr | percent | swing
    atr_multiple: float = 2.0
    stop_percent: float = 5.0
    reward_multiple: float = 2.0         # target = reward_multiple x risk
    max_position_pct: float = 25.0       # cap any single name

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @staticmethod
    def safe_defaults() -> "RiskSettings":
        return RiskSettings()


@dataclasses.dataclass
class Candidate:
    symbol: str
    sector: str
    side: str                  # LONG | SHORT
    signal: str                # BUY | SELL | AVOID
    last_price: float
    entry: float
    stop: float
    target: float
    risk_per_share: float
    reward_per_share: float
    rr: float
    quantity: int
    position_value: float
    capital_at_risk: float
    expected_profit: float
    expected_loss: float
    probability: Probability
    expected_move_pct: float | None
    rsi: float | None
    trend: str
    volume_change_pct: float | None
    relative_volume: float | None
    delivery_pct: float | None
    sector_strength: str
    market_alignment: str
    score: float
    rank: int
    notes: str = ""

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["probability"] = self.probability.to_dict()
        for k, v in list(d.items()):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                d[k] = None
        return d


# --------------------------------------------------------------------------- #
def _trend_label(row) -> str:
    a50 = bool(row.get("above_sma50", 0))
    a200 = bool(row.get("above_sma200", 0))
    if a50 and a200:
        return "Uptrend"
    if not a50 and not a200:
        return "Downtrend"
    return "Sideways"


def _sector_strength(sector: str, sector_ranks: dict[str, float]) -> str:
    p = sector_ranks.get(sector)
    if p is None:
        return "Unknown"
    if p >= 0.8:
        return "Strong"
    if p >= 0.6:
        return "Firm"
    if p >= 0.4:
        return "Neutral"
    if p >= 0.2:
        return "Weak"
    return "Very weak"


def _market_alignment(side: str, market_trend: str) -> str:
    if market_trend == "Unknown":
        return "Unknown"
    bullish = market_trend in ("Bullish", "Strong bullish")
    bearish = market_trend in ("Bearish", "Strong bearish")
    if side == "LONG":
        return "Aligned" if bullish else ("Against" if bearish else "Neutral")
    return "Aligned" if bearish else ("Against" if bullish else "Neutral")


def compute_levels(price: float, atr: float, side: str,
                   rs: RiskSettings) -> tuple[float, float, float]:
    """Return (entry, stop, target)."""
    entry = float(price)
    if rs.stop_method == "percent" or not np.isfinite(atr) or atr <= 0:
        dist = entry * rs.stop_percent / 100.0
    else:
        dist = float(atr) * rs.atr_multiple
    dist = max(dist, entry * 0.005)         # never a nonsense-tight stop

    if side == "LONG":
        stop = entry - dist
        target = entry + dist * rs.reward_multiple
    else:
        stop = entry + dist
        target = entry - dist * rs.reward_multiple
    return entry, stop, target


def size_position(entry: float, stop: float, rs: RiskSettings,
                  capital_remaining: float) -> tuple[int, float, float]:
    """Risk-based sizing. Returns (quantity, position_value, capital_at_risk)."""
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0 or entry <= 0:
        return 0, 0.0, 0.0

    risk_budget = rs.capital * rs.risk_per_trade_pct / 100.0
    qty = int(risk_budget // risk_per_share)

    # cap by single-position limit and by remaining capital
    max_value = min(rs.capital * rs.max_position_pct / 100.0, capital_remaining)
    if qty * entry > max_value:
        qty = int(max_value // entry)

    qty = max(qty, 0)
    return qty, qty * entry, qty * risk_per_share


# --------------------------------------------------------------------------- #
def generate_candidates(daily: pd.DataFrame, ranked: pd.DataFrame,
                        *, sectors: dict[str, str],
                        sector_ranks: dict[str, float],
                        market_trend: str,
                        rs: RiskSettings,
                        calibrator: Calibrator | None = None,
                        delivery: dict[str, float] | None = None,
                        top_n: int = 5) -> dict[str, list[Candidate]]:
    """Build LONG and SHORT candidate lists with levels and sizing."""
    if ranked is None or ranked.empty:
        return {"long": [], "short": []}

    delivery = delivery or {}
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])

    # cache last-bar indicators per symbol
    feats: dict[str, Any] = {}
    for sym, g in d.groupby("symbol"):
        if len(g) < 60:
            continue
        ind = add_indicator_set(g)
        feats[sym] = ind.iloc[-1]

    out: dict[str, list[Candidate]] = {"long": [], "short": []}
    want_long = rs.direction in ("long", "both")
    want_short = rs.direction in ("short", "both")

    pools = []
    if want_long:
        pools.append(("LONG", ranked.head(40).itertuples(), False))
    if want_short:
        pools.append(("SHORT", ranked.tail(40).iloc[::-1].itertuples(), True))

    for side, rows, _rev in pools:
        bucket = out["long"] if side == "LONG" else out["short"]
        capital_remaining = rs.capital
        rank_i = 0

        for r in rows:
            if len(bucket) >= top_n:
                break
            f = feats.get(r.symbol)
            if f is None:
                continue
            price = float(f["close"])
            atr = float(f.get("atr14", np.nan))
            if not np.isfinite(price) or price <= 0:
                continue

            trend = _trend_label(f)
            # Do not fight the stock's own trend.
            if side == "LONG" and trend == "Downtrend":
                continue
            if side == "SHORT" and trend == "Uptrend":
                continue

            entry, stop, target = compute_levels(price, atr, side, rs)
            qty, pos_val, at_risk = size_position(entry, stop, rs,
                                                  capital_remaining)
            if qty <= 0:
                continue
            capital_remaining -= pos_val
            rank_i += 1

            risk_ps = abs(entry - stop)
            reward_ps = abs(target - entry)
            rr = reward_ps / risk_ps if risk_ps > 0 else 0.0

            score = float(r.score)
            prob = (calibrator.probability_for(score, side)
                    if calibrator else INSUFFICIENT)

            # mean_return is the stock's average next-session move for this
            # bucket. For a short, the move in the trade's favour is its
            # negative.
            exp_move = (prob.mean_return * 100
                        if (prob.available and prob.mean_return is not None)
                        else None)
            if side == "SHORT" and exp_move is not None:
                exp_move = -exp_move

            sector = sectors.get(r.symbol, "Unknown")
            sig = "BUY" if side == "LONG" else "SELL"
            align = _market_alignment(side, market_trend)
            if align == "Against":
                sig = "AVOID"

            vol_chg = None
            relvol = None
            if np.isfinite(f.get("vol_z", np.nan)):
                relvol = float(f["volume"] / f["adv20"]) \
                    if f.get("adv20") else None
                vol_chg = ((relvol - 1) * 100) if relvol else None

            bucket.append(Candidate(
                symbol=r.symbol, sector=sector, side=side, signal=sig,
                last_price=round(price, 2), entry=round(entry, 2),
                stop=round(stop, 2), target=round(target, 2),
                risk_per_share=round(risk_ps, 2),
                reward_per_share=round(reward_ps, 2), rr=round(rr, 2),
                quantity=qty, position_value=round(pos_val, 2),
                capital_at_risk=round(at_risk, 2),
                expected_profit=round(qty * reward_ps, 2),
                expected_loss=round(qty * risk_ps, 2),
                probability=prob,
                expected_move_pct=(round(exp_move, 2)
                                   if exp_move is not None else None),
                rsi=(round(float(f["rsi14"]), 1)
                     if np.isfinite(f.get("rsi14", np.nan)) else None),
                trend=trend,
                volume_change_pct=(round(vol_chg, 1)
                                   if vol_chg is not None else None),
                relative_volume=(round(relvol, 2)
                                 if relvol is not None else None),
                delivery_pct=delivery.get(r.symbol),
                sector_strength=_sector_strength(sector, sector_ranks),
                market_alignment=align, score=round(score, 3), rank=rank_i,
            ))
    return out


# --------------------------------------------------------------------------- #
def portfolio_summary(cands: dict[str, list[Candidate]],
                      rs: RiskSettings) -> dict:
    """Capital deployed, at risk, expected P&L (spec item 8)."""
    allc = [c for c in (cands.get("long", []) + cands.get("short", []))
            if c.signal != "AVOID"][:rs.max_positions]

    deployed = sum(c.position_value for c in allc)
    at_risk = sum(c.capital_at_risk for c in allc)
    exp_profit = sum(c.expected_profit for c in allc)
    max_loss = sum(c.expected_loss for c in allc)
    daily_cap = rs.capital * rs.max_daily_loss_pct / 100.0

    return {
        "capital": rs.capital,
        "positions": len(allc),
        "capital_deployed": round(deployed, 2),
        "capital_deployed_pct": round(deployed / rs.capital * 100, 2)
        if rs.capital else 0,
        "capital_at_risk": round(at_risk, 2),
        "capital_at_risk_pct": round(at_risk / rs.capital * 100, 2)
        if rs.capital else 0,
        "max_planned_loss": round(max_loss, 2),
        "expected_profit": round(exp_profit, 2),
        "expected_portfolio_return_pct": round(
            exp_profit / rs.capital * 100, 2) if rs.capital else 0,
        "cash_remaining": round(rs.capital - deployed, 2),
        "daily_loss_limit": round(daily_cap, 2),
        "within_daily_limit": max_loss <= daily_cap,
        "warning": (None if max_loss <= daily_cap else
                    f"Planned worst-case loss Rs {max_loss:,.0f} exceeds your "
                    f"daily limit of Rs {daily_cap:,.0f}. Reduce risk per "
                    f"trade or the number of positions."),
    }
